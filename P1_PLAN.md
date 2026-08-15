# P1 優化規劃

> 前提：P0（URL 正規化去重、同輪動態 seen、extract_json 四層容錯、openai 依賴補齊）已完成並驗證。本規劃在此基礎上處理成本／品質／維護面的優化，**不涉及 model / base_url / openai.OpenAI 呼叫變更**，**不破壞 P0 修復**，**不為遷就改測試預期**（除非是行為本身就該同步調整的測試）。

---

## 現況盤點（regarding 事實，來自程式碼實查）

- `main.py` 目前對三個 watchlist 的搜尋方式：
  - `WATCHLIST`（追蹤議題）：只用 `search_watchlist`（Brave），main.py:43。
  - `RETAIL_HOSPITALITY_WATCHLIST`：`search_watchlist_multi`（Tavily+Exa）**加上** `search_watchlist`（Brave）兩個都打，main.py:46-47。
  - `POS_COMPETITOR_WATCHLIST`：同上，兩個都打，main.py:48-49。
  - `SECURITY_ICG_COMPETITOR_WATCHLIST`：已在程式碼中停用，`competitor_articles = []` 寫死（main.py:50-52 附近有 2026-08 停用註解）。但 `src/watchlist.py` 仍會 `load_topic_list()` 載入這份 json（即使不會拿去搜尋，仍是待清理的殘留設定與 import）。
  - `rotate_half()`（`src/watchlist.py:23-28`）**完全沒有被 main.py 呼叫**，只在 `tests/test_watchlist.py` 被單獨測試，是一個「寫好但沒接線」的函式。
- 三後端從不做「先打 A、沒結果才打 B」的條件判斷，一律全打，是成本超標的主因。
- `discord_send.py`：`MAX_EMBEDS = 10`；固定 1 個 header embed + 最多 9 個 section embed（`len(embeds) >= MAX_EMBEDS: break`），目前非空版面數若 >9 會被**靜默捨棄**、無警告無 log。
- `industry_trends` / `pos_competitors` 定義在 `src/synthesizer.py`（`BRIEFING_TOOL` schema）+ `context.md`（Rule 7/8 prompt 指示）+ `src/formatter.py`（`_build_sections`，硬編 key/label）+ `discord_send.py`（`SECTION_COLORS` 硬編 key）；`pos_retail` 則是走 `sources.json` → `src/sources.py` 的 `SOURCES` 動態驅動的通用 `sections` 迴圈，不在 formatter.py 硬編。三者的定義分散在 4 種不同機制（top-level schema 欄位 / 動態 sources 欄位 / prompt 規則 / 顏色映射），這是合併風險的根源。
- 測試現況缺口：無 `test_brave_search.py`／`test_multi_search.py`，無 `discord_send.py` 測試，無測試涵蓋 main.py 目前「Brave+multi 全打」或未來 fallback 行為，`rotate_half` 只有孤立單元測試、未測整合。

---

## 項目 1：Watchlist 清理（低風險，可獨立先做）

**問題**：`security_icg_competitor_watchlist.json`（Dahua/Axis/Hanwha Vision 安防攝影機 + Stryker/Karl Storz/Olympus/ICG 醫療螢光影像關鍵字）與 `context.md` Rule 9「EXCLUDE: 不要輸出競品/安防產業動態或醫療影像版面」直接衝突——搜尋回來的內容註定被 LLM 丟棄，是純浪費的 API 呼叫。目前程式碼雖已把 `competitor_articles` 寫死為 `[]`（等於已經不搜尋），但設定檔與 import 仍在，屬於「半清理」狀態，容易誤導未來維護者以為這個 watchlist 還在使用。

**具體改動**：
1. `src/watchlist.py`：移除 `SECURITY_ICG_COMPETITOR_WATCHLIST_FILE` 常數、`SECURITY_ICG_COMPETITOR_WATCHLIST = load_topic_list(...)` 這行、以及對應的 import（若有被其他檔案 import 需一併確認，經查目前只有 `src/watchlist.py` 自己定義，main.py 未 import 它）。
2. 刪除 `security_icg_competitor_watchlist.json`（repo root）。
3. `main.py`：移除 `competitor_articles = []` 這行殘留邏輯與相關的 2026-08 停用註解，改為完全不出現這個變數（若 formatter/synthesizer 有依賴 `competitor_articles` 這個 key，需先確認移除後不會造成 KeyError）。
4. 檢查 `sources.json` / `context.md` 是否還有對應 `security`／`icg`／`競品` 版面的殘留設定字串，一併移除（避免 prompt 裡出現「請不要輸出X」但 X 對應的搜尋管線設定卻還留著的矛盾狀態）。

**驗證方式**：
- `grep -ri "security_icg\|SECURITY_ICG" src/ main.py *.json context.md`，確認清理後全域搜尋結果為 0（除了 git history）。
- 跑一次 `main.py`，確認 briefing 輸出無 `competitor_articles`／安防／醫療影像相關版面，且不報錯。

---

## 項目 2：降低 Search API 成本（目標省 60%+）

### 2a. 啟用 `rotate_half()` 做奇偶日輪替（追蹤議題 WATCHLIST）

**現況**：`rotate_half(topics, today=None)` 已完整實作且有 3 個單元測試，只是沒被呼叫。

**具體改動**：
- `main.py:43` 附近，將 `search_watchlist(WATCHLIST)` 改為對 `rotate_half(WATCHLIST)` 的結果做搜尋，而非整份 `WATCHLIST`。
- 確認 `rotate_half` 的 `today` 參數在 main.py 呼叫時使用預設值（UTC now），不需額外傳入，維持函式原本「兩天一個完整週期」的設計。
- 僅套用在 `WATCHLIST`（追蹤議題），**不套用**在 `RETAIL_HOSPITALITY_WATCHLIST` / `POS_COMPETITOR_WATCHLIST`——這兩個是版面內容主力來源，砍半可能造成當日版面內容不足；先只在成本最高、內容重要度相對次要的追蹤議題上做輪替。

**風險與取捨**：
- 輪替代表任一議題每兩天才會被搜尋一次，若當日恰好有該議題的重大新聞，可能延遲一天才被抓到。此為預期取捨，需與使用者確認可接受。
- 若清單長度為奇數，`rotate_half` 目前邏輯是「多出來的一則分給前半」（`midpoint = (len+1)//2`），意味著前半天搜尋量恆大於等於後半天，屬既有行為、非新增風險。

### 2b. 重構 multi_search / brave 呼叫順序為「Brave 優先，無結果才 fallback」

**現況**：`RETAIL_HOSPITALITY_WATCHLIST` 與 `POS_COMPETITOR_WATCHLIST` 目前是 `search_watchlist_multi()`（Tavily+Exa）與 `search_watchlist()`（Brave）**兩個都無條件呼叫**、結果用 `+=` 合併，是三後端同議題三連打的成本主因。

**具體改動**：
- 在 main.py 對這兩個 watchlist 的搜尋邏輯，改為先呼叫 `search_watchlist(topics)`（Brave），檢查回傳結果數量，只有低於門檻值（例如：總筆數 < 某個閾值，或需求上更細緻的「每個 topic 個別判斷」）時才呼叫 `search_watchlist_multi(topics)` 補足。
- **關鍵限制（已由程式碼實查確認）**：`search_watchlist` / `search_watchlist_multi` 是**整份清單一次打完**的函式（`list[str]` → `list[dict]`），不是逐 topic 呼叫。若要做到「每個議題各自判斷 Brave 夠不夠、不夠才對該議題單獨補 Tavily/Exa」，需要把呼叫粒度從「整份清單」改成「逐 topic 迴圈」，即改用 `search_topic()` / `search_topic_multi()`（這兩個逐 topic 版本已存在於 `brave_search.py` / `multi_search.py`）逐一呼叫並判斷。
- 建議分兩階段：
  - **階段 A（低風險，先做）**：整份清單粗粒度判斷——`brave_results = search_watchlist(topics)`；若 `len(brave_results)` 低於某閾值（例如少於 topics 數量的一半），才整份補打 `search_watchlist_multi(topics)`；否則跳過。此法無法個別議題精準判斷，但改動小、風險低，預期仍可省下「Brave 結果本來就充足時」的多後端呼叫。
  - **階段 B（中風險，效果更好，但需求更大改動）**：改為逐 topic 迴圈，每個 topic 先呼叫 `search_topic()`（Brave），該 topic 結果不足才對**這個 topic**額外呼叫 `search_topic_multi()`。此法精準度高，能達成使用者要求的「省 60%+」目標，但屬於呼叫方式的結構性改動，需要在 main.py 新增一個組裝函式（例如 `search_watchlist_with_fallback(topics, threshold)`），並決定放在 `src/multi_search.py` 或 `main.py` 內。
- 門檻值（threshold）建議先設為可調參數（不寫死），初期可用「單一 topic 需要至少 1-2 則結果，Brave 沒有才 fallback」，實際數字待跑幾天實測後微調。

**風險**：
- Brave News API 與 Tavily/Exa 的搜尋品質、時效性不同，改成 fallback 可能讓某些原本靠 Tavily/Exa 補到的獨家新聞消失。建議先跑一週 A/B（同時記錄「若走 fallback 邏輯會省下多少呼叫」但仍照舊全打，觀察差異），再正式切換，降低誤判風險。
- 若選階段 B，逐 topic 迴圈會讓 API 呼叫次數變多次但每次更小（從「幾次批次呼叫」變成「逐 topic 呼叫」），要留意是否有 rate limit 疑慮（尤其 Brave News API）。

**測試案例（2a + 2b）**：
- `test_watchlist.py` 新增：`rotate_half` 整合測試——mock `datetime.utcnow` 分別回傳偶數日期／奇數日期，驗證 main.py 實際餵給 `search_watchlist` 的清單確實是輪替後的半份清單（而非整份 `WATCHLIST`）。
- 新增 `test_main.py` 或獨立 `test_search_fallback.py`：
  - Brave 結果充足（>= 門檻）→ 驗證 `search_watchlist_multi` **未被呼叫**（用 mock/monkeypatch 斷言呼叫次數為 0）。
  - Brave 結果不足（< 門檻）→ 驗證 `search_watchlist_multi` **有被呼叫**，且結果有正確合併（無重複、無遺漏）。
  - Brave 回傳空清單（API key 未設定或無結果）→ 驗證 fallback 有觸發，不會整個 pipeline 掛掉。
  - 若採階段 B：逐 topic 測試，一份清單裡部分 topic Brave 有結果、部分沒有，驗證只有「沒結果」的 topic 有觸發 `search_topic_multi`，其餘 topic 不會被多打。

---

## 項目 3：Prompt Token 前置過濾（每分類只留 top 8-10 篇）

**問題**：目前搜尋+RSS 抓回的文章未經相關性排序過濾就整批塞進 LLM prompt，導致單次呼叫 1.5-2.5 萬 token。

**具體改動**：
- 在 `main.py` 把文章丟進 `src/synthesizer.py` 之前的組裝階段，新增一個「每分類截斷」步驟：對每個分類（追蹤議題／零售餐旅／POS競品／…）的文章清單，依既有的相關性訊號（例如：來源可信度、關鍵字命中數、發布時間新舊）排序後只保留前 8-10 篇。
- 排序依據建議優先使用「現有已算好的訊號」而非新增外部評分機制（避免額外 LLM 呼叫增加成本，違背本項目省成本的目的）。例如可用：
  - 文章標題/摘要是否包含 watchlist 關鍵字命中數（命中越多分數越高）。
  - 發布時間新舊（新聞類版面通常越新越優先）。
  - 若無其他訊號可用，退而求其次用「多後端都有回傳同一篇（去重前重複出現）」視為相關性訊號之一。
- 需要留意：此截斷應發生在 `deduplicator` 去重**之後**、送進 `synthesizer` 之**前**，避免把還沒去重的重複文章誤判為「多來源都認證、優先度高」。
- 此改動不影響 `industry_trends`／`pos_competitors` 等 schema 定義，只影響進 prompt 前的文章數量，屬於 main.py 組裝層的邏輯，不動 `synthesizer.py` 的 model/呼叫方式。

**測試案例**：
- 新增測試：輸入 15 篇模擬文章（不同時間戳、不同關鍵字命中數），驗證輸出只保留 8-10 篇，且保留的確實是排序後分數較高者。
- 邊界案例：分類文章數本身 <8 篇時，不應該被截斷或補空，維持原數量原樣通過。
- 迴歸驗證：截斷前後跑一次完整 pipeline，比對 prompt 組裝出來的字數/token 估算值有明顯下降（可用簡單字數統計，不需真的呼叫 tokenizer）。

---

## 項目 4：discord_send.py 修正

### 4a. 修 `_format_entry` 的 Markdown 殘留 `[]()`

**現況**（已用程式碼實查確認）：
```python
def _format_entry(entry: str, max_len: int = 520) -> str:
    text = entry.strip()
    text = re.sub(r"^\s*[•·]\s*", "", text)
    url = _extract_url(text)
    if url:
        text = text.replace(url, "").replace("  ", " ").strip()
    clean = text
    if len(clean) > max_len:
        clean = clean[: max_len - 1].rstrip() + "…"
    return f"{clean}\n{url}" if url else clean
```

**問題判斷**：目前邏輯是「找出裸網址（`_extract_url`）→ 把網址本身從文字裡挖掉」，但如果原始 entry 是 Markdown 連結格式 `[標題](https://example.com)` 而非裸網址，`_extract_url` 抓到的可能只是括號裡的 URL 部分，`.replace(url, "")` 挖掉 URL 後會留下 `[標題]()` 這種殘骸。

**具體改動**：
- 在 `_extract_url` 呼叫前，先新增一步驟：用正則把 Markdown 連結語法 `[文字](網址)` 轉換成純文字（例如取代成 `文字 網址` 或直接保留 `文字`，網址交給既有的 `_extract_url` + 尾行邏輯處理），避免殘留空括號。
- 具體正則建議：`re.sub(r"\[([^\]]*)\]\((https?://[^)]+)\)", r"\1 \2", text)`，在 `_extract_url(text)` 呼叫之前先跑一次，將 Markdown 連結攤平成「文字 + 空白 + 網址」的純文字，再讓後面既有的 URL 抽取/去重邏輯正常運作。
- 需保留原本「找不到 Markdown 連結格式時完全不影響現有行為」的相容性，此正則只在文字中真的出現 `[]()` 格式時才動作。

**測試案例**：
- 輸入純文字（無連結）→ 輸出不變。
- 輸入裸網址（現有情境）→ 輸出行為不變（回歸測試，確保沒改壞既有邏輯）。
- 輸入 Markdown 連結 `[某新聞標題](https://example.com/a)` → 輸出應為乾淨的「某新聞標題\nhttps://example.com/a」，不含殘留 `[]()`。
- 輸入文字中間夾雜 Markdown 連結（非開頭）→ 同樣要正確攤平，不留殘骸。

### 4b. 控制 embed 總數 ≤9（含 header）

**現況**：`MAX_EMBEDS = 10`，1 個 header + 最多 9 個 section embed，目前非空版面數 >9 時用 `break` **靜默丟棄**多出來的版面，無任何 log/警告。

**問題**：使用者要求「控制 embed 總數 ≤9」——這比目前的 10（1 header + 9 section）再收緊一階，且無論如何都該加上「被丟棄時要留痕跡」的機制，避免內容悄悄消失卻無人知曉。

**具體改動**：
- 若要嚴格滿足「總數 ≤9」：可選擇 (a) 把 `MAX_EMBEDS` 從 10 調整為 9（header 佔 1，section 最多 8），或 (b) 維持 header+9 section=10 但額外加保護（若使用者真正在意的是「目前 10 剛好觸頂，一多任何東西就會被丟」這個**脆弱性**，而非精確數字 9，選項 (b) 加日誌可能更貼近實際需求，屬於待確認的開放問題，見下方 Open Questions）。
- 無論選哪個方案，都要在 `build_embeds`（main 迴圈 `if len(embeds) >= MAX_EMBEDS: break` 那段）新增：當偵測到「還有非空版面但即將被 break 丟棄」時，寫一行 log（例如 `logging.warning(f"embed 數量已達上限，捨棄版面：{remaining_section_labels}")`），讓維護者至少能從 log 得知哪些版面被丟了，而非完全無聲。
- 此改動與項目 5（版面整併）互相牽動：若項目 5 把 3 個版面合併成 2 個，version 之後的版面總數會下降，`MAX_EMBEDS` 觸頂的急迫性會降低，但仍建議先加上日誌機制作為長期保護，不依賴「版面數剛好夠用」這種脆弱假設。

**測試案例**：
- 版面數 <=8（含 header 後 <=9）→ 全部正常輸出，不觸發 break，不寫 log。
- 版面數剛好等於門檻 → 全部輸出，不觸發捨棄邏輯（邊界值測試）。
- 版面數超過門檻 →驗證：(1) 輸出 embed 總數等於門檻值，(2) 多餘版面被正確捨棄，(3) log 有正確記錄被捨棄的版面名稱與數量。

---

## 項目 5：版面整併（高風險，建議分階段）

**目標**：`industry_trends`（AI 零售/餐飲/Hotel 應用趨勢）、`pos_competitors`（POS/Kiosk/Self-checkout 競品動態）、`pos_retail`（走 `sources.json` 動態版面）三者高度重疊，規劃合併為 2 個版面：`retail_hospitality_ai`（場域 AI 應用）+ `pos_kiosk_dynamics`（硬體/競品）。

**為何列為高風險**：這三個版面的定義**分散在 4 種不同機制**，且耦合方式各不相同：
1. `src/synthesizer.py` 的 `BRIEFING_TOOL` schema——`industry_trends`/`pos_competitors` 是 top-level 陣列欄位（且在 `required` 清單內），`pos_retail` 則是巢狀在 `sections` 物件底下（不在 top-level required）。**三者的 schema 位置不對稱**，代表它們不是「同一種版面机制的三個實例」，而是历史上分批用不同方式加上去的。合併時不能只改 prompt，schema 結構本身要重新設計。
2. `src/formatter.py` 的 `_build_sections`——`industry_trends`/`pos_competitors` 是**硬編**在函式裡的 key/label（第 58-72 行附近），`pos_retail` 走的是**動態**的 `SOURCES`（來自 `sources.json`）驅動的通用迴圈。合併後的兩個新版面要嘛都走硬編、要嘛都走動態，需要決定統一走哪一種機制，且要同步搬動程式碼位置。
3. `context.md` Rule 7/8——prompt 端的觸發指示（版面標題文字、篇數要求 4-6 條 / 3-5 條）要重寫成新版面的說法，且要注意 Rule 9 的 EXCLUDE 邏輯（安防/醫療影像）是否還適用、有無交互影響。
4. `discord_send.py` 的 `SECTION_COLORS`——目前只有 `industry_trends`/`pos_competitors` 有色碼設定，沒有 `pos_retail`（它走 fallback 藍色）。新版面需要新增/調整色碼設定，且如果新版面 key 名稱跟舊的不同，舊資料/舊測試 fixture 都要跟著更名。

**牽動檔案清單**：
- `src/synthesizer.py`：`BRIEFING_TOOL` schema 定義、`required` 清單、fallback synthesize 輸出（目前 fallback 寫死 `"industry_trends": []`, `"pos_competitors": []`，需同步改名/改結構）。
- `src/formatter.py`：`_build_sections` 硬編邏輯（第 58-72 行附近）。
- `context.md`：Rule 7、Rule 8（可能還有 Rule 9 交互影響）需要重寫版面觸發規則與篇數要求。
- `discord_send.py`：`SECTION_COLORS` dict 新增/調整版面色碼。
- `sources.json`：若 `pos_retail` 的定義搬過去或搬過來，這份設定檔要跟著調整。
- `tests/test_formatter.py`：目前有 `industry_trends`/`pos_competitors` fixture（第 87-88 行附近），需要同步改名或新增新版面的測試資料。
- 可能還有：任何下游依賴這三個 key 名稱的歷史資料/dashboard/歸檔腳本（本次盤點未涵蓋，需在動手前額外 grep 一次 `industry_trends\|pos_competitors\|pos_retail` 全 repo，確認沒有遺漏的依賴點）。

**前後相容策略建議**：
- **不要一次到位直接刪除舊版面 key。** 建議分兩階段：
  - **階段 1（本次可做）**：先只在 `context.md` prompt 層面調整措辭、統一「場域 AI 應用」與「硬體/競品」的分類邊界描述，讓 LLM 產出的內容更聚焦、減少實質重疊的內容（即使 schema 上仍是 3 個獨立欄位），觀察幾天實際輸出，確認新的分類邊界在內容上站得住腳。
  - **階段 2（後續才做，需要使用者再次確認範圍）**：等階段 1 驗證過內容邊界合理後，才動 schema／formatter／discord 三處的結構性合併，且合併當天建議保留舊 key 的 fallback 相容（例如 formatter 讀取新 key 讀不到時退回讀舊 key），至少撐過一次版本切換的觀察期，再正式移除舊 key。
- 若使用者評估風險後認為可以一次到位（不分階段），至少要求：**在切換前後各跑一次完整 pipeline 並人工比對兩天的 Discord 輸出**，確認版面數變化、embed 是否仍在上限內、內容有沒有因合併而遺漏原本該出現的類別。

**測試案例**：
- Schema 測試：合併後的 `BRIEFING_TOOL` schema 在 `required` 與巢狀結構上是否自洽（例如新兩個版面應該對稱地都放在同一層級，而非一個 top-level 一個巢狀）。
- Formatter 測試：新版面 key 能正確產生 label/entries，且舊 key（如果保留 fallback 相容）在讀不到新 key 時能正確退回。
- Discord 測試：新版面色碼有對應設定，不會 fallback 到預設藍色（除非那是預期行為）。
- 迴歸測試：確認合併後「篇數要求」（原本 4-6 條 + 3-5 條，合併後多少條合理）有明確定義並在測試裡斷言，避免合併後版面內容變得又臭又長或過度稀疏。

**Open Questions（需使用者確認再動工，尤其項目 5）**：
1. 項目 4b「embed 總數 ≤9」是要嚴格改成 9（header+8 section），還是使用者真正在意的是「加上捨棄時的 log 保護」，數字本身可以維持 10？
2. 項目 5 是否接受分兩階段（先只調 prompt 措辭、觀察後才動 schema），還是希望本次就直接做結構性合併？
3. 項目 2b 的 fallback 門檻值（多少筆結果算「Brave 夠不夠」）希望先用什麼初始值，還是要先跑資料觀察後再定？
4. 項目 3 的相關性排序訊號，除了關鍵字命中數/時間新舊，使用者手上是否已有其他既有訊號（例如來源白名單權重）可以直接借用，避免重新設計一套排序邏輯？

---

## 建議實作順序（供後續交給 Codex 執行時參考）

1. 項目 1（watchlist 清理）——最低風險，可獨立先做，且是待清理的技術債。
2. 項目 4a（Markdown `[]()` 修正）——單一函式的 bug fix，風險低、範圍小。
3. 項目 2a（`rotate_half` 接線）——函式已存在且已測試，只是接線，風險可控。
4. 項目 4b（embed ≤9 + log 保護）——需先確認 Open Question 1 的方向。
5. 項目 2b 階段 A（粗粒度 Brave-first fallback）——需先確認 Open Question 3 的門檻值。
6. 項目 3（prompt token 前置過濾）——需先確認 Open Question 4 的排序訊號來源。
7. 項目 2b 階段 B（逐 topic fallback，若階段 A 效果不足以達到 60% 省下目標才需要）。
8. 項目 5（版面整併）——待前述項目穩定後，且使用者對 Open Question 2 的分階段方式拍板後再動工。
