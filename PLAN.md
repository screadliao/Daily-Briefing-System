# P0 修復規劃：早報新聞重複 + 分析易降級 fallback

> 規劃者：Claude Code（僅規劃，不寫程式碼）。實作交給 Codex。
> 範圍嚴格限定下列 4 點，禁止動 `model="gpt-5.6-terra"`、`base_url`、核心 LLM 呼叫方式，不做 P1（rotate_half / section 合併 / embed 合併）。

## 背景與根因

1. **重複新聞**：`src/deduplicator.py` 的 `seen_urls` 只做字串完全比對，沒有 URL 正規化（`utm_*`/`ref`/`fbclid` query string、結尾斜線、scheme 大小寫都會讓同一篇文章被判定成不同 URL）。且 `main.py` 的 `_filter_article_list`/`_filter_article_groups` 是純函式式過濾，`seen_urls` 在同一輪處理多個來源（`raw_articles` / `brave_articles` / `retail_hospitality_articles` / `pos_competitor_articles` / `competitor_articles`）時完全不變、不累積，導致同一天不同來源撈到同一篇文章的不同 URL 變體時無法互相去重。
2. **分析降級 fallback**：`src/synthesizer.py:extract_json`（第 250-258 行）在 `json.loads` 失敗時用貪婪正規表達式 `re.search(r"\{.*\}", candidate, re.DOTALL)` 抓 JSON。當 LLM 回應包含 markdown code fence（` ```json ... ``` `）或輸出被截斷時，這個正則會抓到錯誤範圍或抓不到合法 JSON，`json.loads` 再次拋錯 → 每次重試都失敗 → 觸發 `build_fallback_briefing`。
3. `requirements.txt` 缺 `openai`，`.venv` 裡有裝但沒宣告，環境重建時會缺套件。

## 修改檔案清單

- `src/deduplicator.py`：新增 `normalize_url()`，`load_seen_urls`/`_normalize_entries` 存入時正規化。
- `main.py`：`_filter_article_list`/`_filter_article_groups` 改為動態累積 `seen` set，同輪跨來源去重；呼叫處用正規化後的 URL 比對。
- `src/synthesizer.py`：`extract_json` 加固（去 code fence、修復性解析、部分提取 fallback）。
- `requirements.txt`：新增 `openai>=1.40.0`。

---

## 1) `src/deduplicator.py` — `normalize_url()`

### 新增函式

```python
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_EXACT = {"ref", "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "spm", "from"}


def normalize_url(url: str) -> str:
    """正規化 URL 供去重比對：小寫 scheme/host、去追蹤參數、去尾斜線、去 fragment。"""
    if not url:
        return url
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not (k.lower().startswith(_TRACKING_PARAM_PREFIXES) or k.lower() in _TRACKING_PARAM_EXACT)
    ]
    query_pairs.sort()  # 參數順序不同也視為同一 URL
    query = urlencode(query_pairs)
    return urlunsplit((scheme, netloc, path, query, ""))  # 丟棄 fragment
```

- 邊界情況：空字串、`None`（呼叫端已用 `isinstance(url, str) and url` 檔掉，此函式內仍保留 guard 以防單元測試直接呼叫）、沒有 query 的 URL、只有追蹤參數的 URL（正規化後 query 變空字串）。
- **不處理**：非 http(s) scheme（如 `mailto:`）維持原樣通過 `urlsplit`，不特別擋（超出 P0 範圍）。

### 套用位置

- `_normalize_entries()`（第 51-63 行）：`url = item.get("url")` 之後，改成 `url = normalize_url(url)` 再存入 `entries` dict（key 正規化後才不會同一篇文章因兩種寫法各存一筆）。
- `save_seen_urls()`（第 66-90 行）：
  - `for url in seen:` 迴圈裡的 `url` 也要 `normalize_url(url)` 再 `entries.setdefault(...)`。
  - `for article in new_articles:` 裡 `url = article.get("url")` 也要正規化後再存。
- `load_seen_urls()` 讀 remote/local payload 時不用額外改，因為已經統一由 `_normalize_entries` 處理。

---

## 2) `main.py` — 動態 seen set，同輪跨來源去重

### 問題重述

目前呼叫序（第 53-64 行）：

```python
seen_urls = load_seen_urls()
raw_articles, raw_filtered, raw_total = _filter_article_groups(raw_articles, seen_urls)
brave_articles, brave_filtered, brave_total = _filter_article_list(brave_articles, seen_urls)
retail_hospitality_articles, retail_filtered, retail_total = _filter_article_list(retail_hospitality_articles, seen_urls)
pos_competitor_articles, pos_filtered, pos_total = _filter_article_list(pos_competitor_articles, seen_urls)
competitor_articles, competitor_filtered, competitor_total = _filter_article_list(competitor_articles, seen_urls)
```

`seen_urls` 是同一個 set 物件被傳入 5 次，但函式內部從不寫回這個 set，所以來源 A 和來源 B 各自撈到同一篇文章時，兩邊都判定「不在 seen_urls 裡」而同時保留 → 當日重複。

### 修改方式

**`_filter_article_list`（第 130-143 行）**：改成同時比對並「就地」把本輪已通過的 URL 正規化後寫回傳入的 `seen_urls`（mutate in place，呼叫端不需要改變傳參方式）：

```python
def _filter_article_list(
    articles: list[dict],
    seen_urls: set[str],
) -> tuple[list[dict], int, int]:
    filtered_articles: list[dict] = []
    filtered_count = 0
    total_count = len(articles)
    for article in articles:
        url = article.get("url")
        normalized = normalize_url(url) if isinstance(url, str) and url else None
        if normalized and normalized in seen_urls:
            filtered_count += 1
            continue
        if normalized:
            seen_urls.add(normalized)  # 本輪內動態累積，跨來源即時生效
        filtered_articles.append(article)
    return filtered_articles, filtered_count, total_count
```

- 需要 `from src.deduplicator import load_seen_urls, save_seen_urls, normalize_url`（第 13 行加上 `normalize_url`）。
- **注意**：`seen_urls` 一開始是 `load_seen_urls()` 回傳的正規化後 URL set（已由第 1 節保證），所以這裡比對時也要用正規化後的 URL 比對，避免「歷史 seen」是正規化格式、但當輪新抓的還是原始格式而永遠比不中。

**`_filter_article_groups`（第 115-127 行）**：不需要額外改動——因為它內部呼叫 `_filter_article_list` 時傳的就是同一個 `seen_urls`，只要 `_filter_article_list` 改成 mutate-in-place，`_filter_article_groups` 對 `article_groups` 裡各 category 之間也會自動跨 category 去重。

**呼叫序影響**：因為 `_filter_article_list` 現在會 mutate `seen_urls`，第 53-64 行原本的呼叫序不用改寫法，但函式呼叫的「先後順序」現在有意義：先處理的來源，其 URL 會先被加入 seen_urls，後處理的來源才吃得到。目前順序（raw → brave → retail → pos → competitor）本身沒有問題，維持現狀即可，只需在 PR 說明加註解提醒未來不要隨意調換順序或改成平行處理。

**`save_seen_urls` 呼叫（第 94-99 行附近）**：因為傳入的 `seen_urls` 現在已經包含本輪所有來源新增的 URL（因為被 mutate），`save_seen_urls` 內的 `for url in seen:` 迴圈本來就會把這些新 URL 存回去 —— 這其實是原本設計就預期的行為（`seen` 參數本來就是要被存檔），只是過去因為沒有真的被填入本輪新 URL，跨來源去重才失效。這個修法是「補上遺漏的設計」，不是新增副作用。

---

## 3) `src/synthesizer.py` — `extract_json` 加固

### 現況（第 250-258 行）

```python
def extract_json(raw_text: str) -> dict[str, Any]:
    candidate = raw_text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        if not match:
            raise ValueError("Model response does not contain JSON object.")
        return json.loads(match.group(0))
```

### 改法（分層 fallback，逐層失敗才往下一層，只在最後仍失敗才 raise）

```python
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(raw_text: str) -> dict[str, Any]:
    candidate = raw_text.strip()

    # Layer 1：直接解析
    parsed = _try_json_loads(candidate)
    if parsed is not None:
        return parsed

    # Layer 2：剝除 ```json ... ``` code fence 後再解析
    fence_match = _CODE_FENCE_RE.search(candidate)
    if fence_match:
        parsed = _try_json_loads(fence_match.group(1).strip())
        if parsed is not None:
            return parsed

    # Layer 3：用「第一個 { 到最後一個對應的 }」做非貪婪配對括號掃描
    #（比貪婪正則更能容忍截斷/多餘文字，找不到合法配對就放棄這層）
    balanced = _extract_balanced_object(candidate)
    if balanced is not None:
        parsed = _try_json_loads(balanced)
        if parsed is not None:
            return parsed

    # Layer 4：截斷修復 —— 嘗試補齊常見的未閉合括號/引號（僅處理"結尾被切斷"的情況）
    repaired = _try_repair_truncated_json(candidate)
    if repaired is not None:
        return repaired

    raise ValueError("Model response does not contain valid JSON object.")


def _try_json_loads(text: str) -> dict[str, Any] | None:
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return None
    return result if isinstance(result, dict) else None


def _extract_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None  # 沒找到配對完整的區塊（可能被截斷）


def _try_repair_truncated_json(text: str) -> dict[str, Any] | None:
    """對明顯被截斷（缺收尾括號/引號）的輸出做保守修復，抓不到就回傳 None（走 raise）。"""
    start = text.find("{")
    if start == -1:
        return None
    truncated = text[start:]
    # 補齊未閉合的字串引號
    if truncated.count('"') % 2 == 1:
        truncated += '"'
    # 補齊未閉合的 [ 和 {
    open_braces = truncated.count("{") - truncated.count("}")
    open_brackets = truncated.count("[") - truncated.count("]")
    truncated = truncated.rstrip().rstrip(",")
    truncated += "]" * max(open_brackets, 0) + "}" * max(open_braces, 0)
    return _try_json_loads(truncated)
```

- 設計原則：**每一層只做「更保守」的事**，第 1 層失敗才碰第 2 層，避免原本能直接 parse 的正常回應被不必要的字串操作影響。
- Layer 3 取代原本的貪婪正則，用括號配對掃描找到「第一個完整、平衡的 `{...}`」，比 `re.DOTALL` 貪婪匹配更精準（貪婪正則會抓到文字中最後一個 `}`，若前後有多個 JSON-like 區塊或說明文字會抓錯範圍）。
- Layer 4（截斷修復）是新增能力，處理 LLM 輸出被 token 上限截斷、收尾括號沒打完的情況——這是目前最常見的「已知會 fallback」情境之一。
- 呼叫端（第 173 行 `return extract_json(raw_text)`）不需要改，介面不變（輸入 str，輸出 dict，失敗仍 raise ValueError）。

---

## 4) `requirements.txt`

在合理位置（依現有字母序，`jinja2` 與 `lxml` 之間）新增：

```
openai>=1.40.0
```

---

## 測試案例清單

### `tests/test_deduplicator.py`（新增或擴充）

1. `normalize_url` 去除 `utm_source`/`utm_medium`/`utm_campaign` 等追蹤參數，其餘參數保留。
2. `normalize_url` 去除 `ref`、`fbclid`、`gclid` 等單一追蹤參數。
3. `normalize_url` 去除結尾多餘斜線：`https://a.com/x/` == `https://a.com/x`。
4. `normalize_url` scheme 大小寫不敏感：`HTTPS://A.com/x` 與 `https://a.com/x` 正規化後相同。
5. `normalize_url` 忽略 fragment：`https://a.com/x#section` == `https://a.com/x`。
6. `normalize_url` 對只剩追蹤參數的 URL 正規化後 query 為空字串，且不影響比對。
7. `normalize_url` 對空字串/`None` 呼叫不拋例外（回傳原值或空字串）。
8. `_normalize_entries` 讀入含有兩種寫法（bare / 帶 utm）指向同一篇文章的 entries 時，去重後只留一筆（因為 key 已正規化）。
9. `save_seen_urls` 存檔時，`seen` 參數裡的原始 URL 與正規化後的 URL 若對應同一篇文章，寫入的 JSON 裡只出現一次。

### `tests/test_main.py`（新增或擴充，測 `_filter_article_list`/`_filter_article_groups`）

10. 同一輪呼叫中，來源 A 有 `https://a.com/x?utm_source=rss`，來源 B 有 `https://a.com/x`：先處理 A 的 `_filter_article_list` 後，`seen_urls` 應包含正規化後的 URL；接著處理 B 時，B 裡的同一篇文章應被過濾掉（`filtered_count` 遞增）。
11. `_filter_article_groups` 內，同一個 `article_groups` 底下兩個不同 category 出現同一篇文章（URL 相同或帶不同追蹤參數）時，只有第一次出現的 category 保留該文章，第二次被過濾。
12. `seen_urls`（來自 `load_seen_urls()` 模擬歷史紀錄）裡已有一篇文章的正規化 URL，本輪任一來源撈到該文章（不論是否帶追蹤參數）都應被過濾，且不會誤傷同 domain 的不同文章。
13. 呼叫序驗證：raw → brave → retail → pos → competitor 依序處理後，`seen_urls` 累積的文章數 == 5 組來源中「去重後不重複的文章總數」。
14. `_filter_article_list` 對沒有 `url` 欄位或 `url` 為空字串的文章，不觸碰 `seen_urls`，同時仍保留該文章在輸出中（維持現行行為）。

### `tests/test_synthesizer.py`（新增或擴充，測 `extract_json`）

15. 純 JSON 字串（無 markdown、無多餘文字）→ 直接透過 Layer 1 解析成功。
16. LLM 回應包在 ` ```json {...} ``` ` code fence 裡 → Layer 2 成功剝除後解析。
17. LLM 回應包在無語言標記的 ` ``` {...} ``` ` code fence 裡 → Layer 2 仍能處理。
18. JSON 前後有額外說明文字（例如「這是分析結果：{...} 以上為結果」）→ Layer 3 括號配對掃描抓出正確範圍。
19. JSON 內部字串值中含有 `{`/`}` 字元（例如摘要文字提到程式碼片段）→ Layer 3 的括號配對要正確跳過字串內容，不誤判深度。
20. 輸出被截斷、缺少收尾 `}`（模擬 token 上限）→ Layer 4 修復後可解析出部分正確欄位。
21. 輸出被截斷在字串值中間（缺收尾引號 + 收尾括號）→ Layer 4 修復後仍可解析。
22. 完全非 JSON 的純文字回應（無 `{`）→ 四層皆失敗，正確 raise `ValueError`。
23. 空字串輸入 → raise `ValueError`，不拋出未預期例外（如 IndexError）。
24. 舊測試（若原本有測 `extract_json` 基本情境的 test）需保留並通過，確認向下相容。

### 套件/環境

25. `pip install -r requirements.txt`（或 `.venv` 重建）後 `import openai` 成功，且版本符合 `>=1.40.0`。

---

## 驗證方式

1. **單元測試**：`pytest tests/test_deduplicator.py tests/test_main.py tests/test_synthesizer.py -v`，確認上述 25 個案例全過，且既有測試無迴歸（跑全量 `pytest`）。
2. **去重回歸驗證**：用近期一份實際 `_site/seen_urls.json` + 一組已知含 utm 參數重複文章的樣本資料，手動呼叫 `_filter_article_groups`/`_filter_article_list` 驗證重複文章確實被濾掉、且正常新文章不被誤殺（避免正規化過度導致誤判不同文章為同一篇）。
3. **extract_json 回歸驗證**：收集近期幾則觸發過 fallback 的實際 LLM 原始回應（若有存 log），跑過新版 `extract_json` 確認能正確解析，不再進 fallback。若無歷史 log，用人工建構的截斷/code-fence 樣本驗證。
4. **端到端 dry-run**：`python main.py --dry-run`（或專案既有的 dry-run 參數）跑一次完整流程，確認：
   - 沒有 `ModuleNotFoundError: openai`。
   - 產出的 briefing JSON 中沒有明顯重複文章（用 URL 正規化後比對）。
   - 若當日 LLM 正常回應，不應該落入 `build_fallback_briefing`（可在 log 或回傳結構中確認走的是正常 synthesize 路徑，而非 fallback 標記）。
5. **不變性檢查**：`git diff` 確認除上述 4 個檔案外無其他檔案變動，且 `model="gpt-5.6-terra"`、`base_url`、`openai.OpenAI(...)` 呼叫參數未被觸碰。
