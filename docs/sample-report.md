# Migration Report — gpt-4o-mini-2024-07-18 → claude-haiku-4-5

- **Corpus:** `corpus`
- **Target:** `claude-haiku-4-5` (anthropic)
- **Generated:** 2026-06-13T07:01:21+00:00
- **Comparators:** exact, fuzzy
- **Prompts:** 100 compared (100 from corpus cache, 0 live), 0 skipped, 0 errored
- **Output tokens:** baseline 1,435 → target 3,059 (2.13×, over 100 prompts)
- **Est. cost (anthropic-list+openai-list):** baseline $0.001658 → target $0.020655 (12.46×, over 100 priced rows)

> **Verdict:** exact 22/100 passed · mean 0.22 · fuzzy 48/100 passed · mean 0.65

## Summary

| Comparator | Compared | Passed | Pass rate | Mean score |
|---|---:|---:|---:|---:|
| exact | 100 | 22/100 | 22% | 0.22 |
| fuzzy | 100 | 48/100 | 48% | 0.65 |

## By category

_Cells are pass rate · mean score. Out tokens and Latency are target/baseline ratios._

| Category | Prompts | exact | fuzzy | Out tokens | Latency | Cost (anthropic-list+openai-list) |
|---|---:|---:|---:|---:|---:|---:|
| classify | 30 | 7% · 0.07 | 13% · 0.25 | 9.40× | – | 25.16× |
| extract | 30 | 57% · 0.57 | 93% · 0.95 | 1.42× | – | 9.69× |
| rewrite | 15 | 13% · 0.13 | 40% · 0.72 | 1.65× | – | 10.45× |
| summarize | 15 | 0% · 0.00 | 7% · 0.62 | 1.18× | – | 8.60× |
| translate | 10 | 10% · 0.10 | 90% · 0.90 | 1.68× | – | 10.89× |

## Results

| # | Prompt | Category | Baseline model | exact | fuzzy | Out tok | Latency | Cost (anthropic-list+openai-list) | Cached |
|---|---|---|---|---|---|---|---|---|---|
| 1 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.98 | 23→32 | – | $0.000024→$0.000227 | ✅ |
| 2 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 23→30 | – | $0.000021→$0.000199 | ✅ |
| 3 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.84 | 45→38 | – | $0.000036→$0.00025 | ✅ |
| 4 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.96 | 12→15 | – | $0.000015→$0.000129 | ✅ |
| 5 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.13 | 2→31 | – | $0.000009→$0.000203 | ✅ |
| 6 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.52 | 1→10 | – | $0.000008→$0.000096 | ✅ |
| 7 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.02 | 2→43 | – | $0.000009→$0.000263 | ✅ |
| 8 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.78 | 32→35 | – | $0.00003→$0.000247 | ✅ |
| 9 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.12 | 48→198 | – | $0.000036→$0.001042 | ✅ |
| 10 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.44 | 19→28 | – | $0.000019→$0.000194 | ✅ |
| 11 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.64 | 29→35 | – | $0.000027→$0.000238 | ✅ |
| 12 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 6→10 | – | $0.000012→$0.000104 | ✅ |
| 13 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.97 | 8→13 | – | $0.000012→$0.000114 | ✅ |
| 14 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 12→18 | – | $0.000015→$0.000142 | ✅ |
| 15 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.52 | 20→33 | – | $0.000019→$0.000209 | ✅ |
| 16 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 23→30 | – | $0.000022→$0.000206 | ✅ |
| 17 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.98 | 25→24 | – | $0.000024→$0.000183 | ✅ |
| 18 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.91 | 15→19 | – | $0.000017→$0.000147 | ✅ |
| 19 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.93 | 16→31 | – | $0.000017→$0.000209 | ✅ |
| 20 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.90 | 16→11 | – | $0.000019→$0.000116 | ✅ |
| 21 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.10 | 1→6 | – | $0.000008→$0.000077 | ✅ |
| 22 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.16 | 3→23 | – | $0.000009→$0.000166 | ✅ |
| 23 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.19 | 3→37 | – | $0.00001→$0.00024 | ✅ |
| 24 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 1→4 | – | $0.000008→$0.000075 | ✅ |
| 25 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 22→29 | – | $0.00002→$0.000192 | ✅ |
| 26 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.24 | 3→29 | – | $0.000009→$0.000195 | ✅ |
| 27 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.05 | 2→54 | – | $0.000009→$0.000322 | ✅ |
| 28 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.71 | 24→30 | – | $0.000025→$0.000224 | ✅ |
| 29 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.61 | 34→31 | – | $0.000031→$0.000224 | ✅ |
| 30 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 7→11 | – | $0.000011→$0.000102 | ✅ |
| 31 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.98 | 21→36 | – | $0.000021→$0.000242 | ✅ |
| 32 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.08 | 3→86 | – | $0.000009→$0.000481 | ✅ |
| 33 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 22→29 | – | $0.000021→$0.000195 | ✅ |
| 34 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.98 | 33→55 | – | $0.000028→$0.000326 | ✅ |
| 35 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.46 | 20→25 | – | $0.000021→$0.000185 | ✅ |
| 36 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.86 | 2→4 | – | $0.00001→$0.000076 | ✅ |
| 37 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | translate | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 10→18 | – | $0.000012→$0.00013 | ✅ |
| 38 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 20→24 | – | $0.000021→$0.000181 | ✅ |
| 39 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.66 | 16→22 | – | $0.000018→$0.000165 | ✅ |
| 40 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.76 | 22→37 | – | $0.000024→$0.000256 | ✅ |
| 41 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.00 | 2→106 | – | $0.000008→$0.000579 | ✅ |
| 42 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.74 | 28→36 | – | $0.000027→$0.000249 | ✅ |
| 43 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.97 | 19→27 | – | $0.000018→$0.00018 | ✅ |
| 44 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 8→12 | – | $0.000012→$0.000111 | ✅ |
| 45 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 2→6 | – | $0.000008→$0.000077 | ✅ |
| 46 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.10 | 1→25 | – | $0.000008→$0.000174 | ✅ |
| 47 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.98 | 19→36 | – | $0.00002→$0.000239 | ✅ |
| 48 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.38 | 20→34 | – | $0.000024→$0.000248 | ✅ |
| 49 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.13 | 3→44 | – | $0.000009→$0.000269 | ✅ |
| 50 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.43 | 7→18 | – | $0.000011→$0.000131 | ✅ |
| 51 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.97 | 19→35 | – | $0.000019→$0.000223 | ✅ |
| 52 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.50 | 15→24 | – | $0.000017→$0.000174 | ✅ |
| 53 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.91 | 24→29 | – | $0.000021→$0.000188 | ✅ |
| 54 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.50 | 3→11 | – | $0.000009→$0.000103 | ✅ |
| 55 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.00 | 2→64 | – | $0.000009→$0.00037 | ✅ |
| 56 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.70 | 10→14 | – | $0.000014→$0.000128 | ✅ |
| 57 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 34→42 | – | $0.000029→$0.000269 | ✅ |
| 58 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.06 | 2→47 | – | $0.000008→$0.000282 | ✅ |
| 59 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.64 | 9→19 | – | $0.000015→$0.000159 | ✅ |
| 60 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.42 | 20→42 | – | $0.00002→$0.000264 | ✅ |
| 61 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 6→9 | – | $0.00001→$0.000087 | ✅ |
| 62 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.99 | 15→24 | – | $0.000015→$0.000161 | ✅ |
| 63 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.80 | 2→4 | – | $0.000009→$0.000069 | ✅ |
| 64 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.97 | 10→14 | – | $0.000012→$0.00011 | ✅ |
| 65 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.70 | 13→26 | – | $0.000016→$0.000186 | ✅ |
| 66 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.44 | 14→33 | – | $0.000015→$0.000212 | ✅ |
| 67 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.52 | 19→56 | – | $0.000019→$0.000329 | ✅ |
| 68 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.92 | 5→9 | – | $0.00001→$0.000092 | ✅ |
| 69 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.47 | 19→22 | – | $0.000021→$0.00017 | ✅ |
| 70 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.90 | 66→91 | – | $0.000048→$0.000511 | ✅ |
| 71 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.93 | 11→21 | – | $0.000013→$0.000148 | ✅ |
| 72 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.63 | 34→42 | – | $0.000032→$0.000287 | ✅ |
| 73 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.46 | 39→35 | – | $0.000035→$0.000255 | ✅ |
| 74 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.17 | 5→24 | – | $0.000011→$0.000172 | ✅ |
| 75 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.70 | 15→35 | – | $0.000015→$0.000218 | ✅ |
| 76 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.97 | 6→11 | – | $0.000011→$0.000102 | ✅ |
| 77 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 8→11 | – | $0.000013→$0.000109 | ✅ |
| 78 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.13 | 2→31 | – | $0.000009→$0.000204 | ✅ |
| 79 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.91 | 16→22 | – | $0.000016→$0.000156 | ✅ |
| 80 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 30→38 | – | $0.000026→$0.000244 | ✅ |
| 81 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.60 | 11→34 | – | $0.000014→$0.000218 | ✅ |
| 82 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.88 | 16→24 | – | $0.000017→$0.000168 | ✅ |
| 83 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.03 | 1→39 | – | $0.000008→$0.000245 | ✅ |
| 84 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.56 | 1→9 | – | $0.000008→$0.000092 | ✅ |
| 85 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 6→10 | – | $0.000012→$0.000103 | ✅ |
| 86 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 25→33 | – | $0.000023→$0.00022 | ✅ |
| 87 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.06 | 4→123 | – | $0.000009→$0.000661 | ✅ |
| 88 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.93 | 30→31 | – | $0.000029→$0.000228 | ✅ |
| 89 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.00 | 1→4 | – | $0.000008→$0.000071 | ✅ |
| 90 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.19 | 2→23 | – | $0.000009→$0.000167 | ✅ |
| 91 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 16→23 | – | $0.000018→$0.000171 | ✅ |
| 92 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.01 | 3→48 | – | $0.000009→$0.000287 | ✅ |
| 93 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 1→4 | – | $0.000008→$0.000075 | ✅ |
| 94 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.12 | 1→29 | – | $0.000008→$0.000193 | ✅ |
| 95 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.88 | 12→20 | – | $0.000014→$0.000142 | ✅ |
| 96 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 9→14 | – | $0.000012→$0.00012 | ✅ |
| 97 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.47 | 39→39 | – | $0.000036→$0.000277 | ✅ |
| 98 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.58 | 22→21 | – | $0.000023→$0.000173 | ✅ |
| 99 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | 2→6 | – | $0.000008→$0.000075 | ✅ |
| 100 | [system] You are a precise assistant. Answer directly and concisely. No preambl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.25 | 5→22 | – | $0.00001→$0.000158 | ✅ |

## Details

### 1. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_04345e5becaf4b35` → `migration__openai_gpt-4o-mini_04345e5becaf4b35__to__claude-haiku-4-5` · semantic key `a899bc4776271cb4b5e44047983c4b5b` · category `extract` · out tokens 23→32

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.98 — sequence similarity 0.98 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {error_code, service} from this log line: '2026-06-11T09:14:02Z payments-api ERROR 5021 connection pool exhausted'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
{
  "error_code": 5021,
  "service": "payments-api"
}
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
{
  "error_code": "5021",
  "service": "payments-api"
}
```
````

</details>

### 2. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_05e4ebf8769f503c` → `migration__openai_gpt-4o-mini_05e4ebf8769f503c__to__claude-haiku-4-5` · semantic key `92b3874852ffcaf60316fecdcc84dc14` · category `extract` · out tokens 23→30

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {amount, currency}: 'Your total comes to $1,249.99 including tax.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
{
  "amount": 1249.99,
  "currency": "USD"
}
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
{
  "amount": 1249.99,
  "currency": "USD"
}
```
````

</details>

### 3. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_06a1e8e45272403f` → `migration__openai_gpt-4o-mini_06a1e8e45272403f__to__claude-haiku-4-5` · semantic key `af537edff7ff190adbcfe9bcc7a3d9cc` · category `extract` · out tokens 45→38

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.84 — sequence similarity 0.84 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {checkin, checkout} as ISO dates: 'We'd like the room from March 3rd to March 7th, 2026.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
{
  "checkin": "2026-03-03T00:00:00Z",
  "checkout": "2026-03-07T00:00:00Z"
}
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
{
  "checkin": "2026-03-03",
  "checkout": "2026-03-07"
}
```
````

</details>

### 4. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_0a2b2c0e469ec41e` → `migration__openai_gpt-4o-mini_0a2b2c0e469ec41e__to__claude-haiku-4-5` · semantic key `bf8582b9de235ac7376c7ef28b970dfc` · category `rewrite` · out tokens 12→15

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.96 — sequence similarity 0.96 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Fix grammar and spelling, return only the corrected text: 'Me and him was going to recieve the package on Wendesday.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
He and I were going to receive the package on Wednesday.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Me and him were going to receive the package on Wednesday.
```

</details>

### 5. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_0d22317379c5e062` → `migration__openai_gpt-4o-mini_0d22317379c5e062__to__claude-haiku-4-5` · semantic key `03be769ed6dcff44db3d26045168f978` · category `classify` · out tokens 2→31

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.13 — sequence similarity 0.13 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Sentiment (positive/negative/neutral): 'Shipping was fast but the product broke within a week.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Negative.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Negative**

The negative aspect (product breaking) outweighs the positive (fast shipping), resulting in overall negative sentiment.
```

</details>

### 6. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_141ed5a1217f8d73` → `migration__openai_gpt-4o-mini_141ed5a1217f8d73__to__claude-haiku-4-5` · semantic key `86de9a66ba804bb78690ac3f291eb44b` · category `classify` · out tokens 1→10

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.52 — sequence similarity 0.52 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Sentiment (positive/negative/neutral): 'Absolutely love it, exceeded every expectation!'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Positive
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Sentiment: **Positive**
```

</details>

### 7. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_18e0f38c9da3089d` → `migration__openai_gpt-4o-mini_18e0f38c9da3089d__to__claude-haiku-4-5` · semantic key `a49ec22ca5d985abc6a7bc862079e686` · category `classify` · out tokens 2→43

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.02 — sequence similarity 0.02 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Is this about a delivery problem? (yes/no): 'The tracking number you sent does not work.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Yes.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
No.

This is about a tracking issue, not a delivery problem. The customer is reporting that the tracking number itself is non-functional, rather than reporting that their delivery has encountered a problem.
```

</details>

### 8. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_19e926d571acae85` → `migration__openai_gpt-4o-mini_19e926d571acae85__to__claude-haiku-4-5` · semantic key `9cb7807a6a3bc91b2dd5a5ba3ef0ba8f` · category `summarize` · out tokens 32→35

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.78 — sequence similarity 0.78 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Summarize this policy in one sentence: 'Employees may work remotely up to three days per week, must be reachable during core hours 10-15, and need manager approval for full-remote arrangements.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Employees can work remotely three days a week with manager approval for full-remote, and must be available during core hours from 10 AM to 3 PM.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Employees can work remotely up to three days weekly with manager approval for full-remote arrangements, provided they remain available during core hours 10-15.
```

</details>

### 9. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_1b7f67df4a19f8dc` → `migration__openai_gpt-4o-mini_1b7f67df4a19f8dc__to__claude-haiku-4-5` · semantic key `cdae929542ed548a8e57aca83344fb80` · category `classify` · out tokens 48→198

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.12 — sequence similarity 0.12 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Topic (billing/bug/feature_request/how_to): 'How do I add a teammate to my workspace?'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
To add a teammate to your workspace, go to the workspace settings, select "Members," and then click on "Invite Team Member" or "Add Member." Enter the email address of the teammate you want to invite and send the invitation.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
# How to Add a Teammate to Your Workspace

1. **Go to Workspace Settings**
   - Click on your workspace name in the top left
   - Select "Settings" or "Members"

2. **Invite Team Members**
   - Click "Add Member" or "Invite"
   - Enter their email address
   - Select their role/permission level

3. **Send Invitation**
   - Click "Send Invite" or "Confirm"
   - They'll receive an email invitation
   - They can accept and join your workspace

4. **Set Permissions** (optional)
   - Assign appropriate access level (Admin, Editor, Viewer, etc.)
   - Configure which projects/resources they can access

**Note:** The exact steps vary by platform. If you need help with a specific tool, provide the workspace name and I can give more detailed instructions.
```

</details>

### 10. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_1dd062aa5ebeed8f` → `migration__openai_gpt-4o-mini_1dd062aa5ebeed8f__to__claude-haiku-4-5` · semantic key `4ef6a39c2f11b0fe317767a4f13e394f` · category `rewrite` · out tokens 19→28

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.44 — sequence similarity 0.44 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Rewrite this error message to be user-friendly: 'ERR_CONN_5021: pool exhausted at gateway.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
"Connection error: We've run out of available resources at the gateway. Please try again later."
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**We're temporarily unable to process your request. Our system is currently at capacity. Please try again in a few moments.**
```

</details>

### 11. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_1e2eb9c3465c2c3c` → `migration__openai_gpt-4o-mini_1e2eb9c3465c2c3c__to__claude-haiku-4-5` · semantic key `93c490dc4ecf4a24b819d50fad2b3808` · category `summarize` · out tokens 29→35

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.64 — sequence similarity 0.64 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Summarize the complaint in one sentence: 'I ordered a blue medium jacket but received a red large, the return label link was broken, and support took four days to respond.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
The complaint is about receiving the wrong jacket (red large instead of blue medium), a broken return label link, and a delayed response from support.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
The customer received an incorrect item (red large instead of blue medium), encountered a broken return label link, and experienced slow customer support response time of four days.
```

</details>

### 12. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_24c804c48a5838fd` → `migration__openai_gpt-4o-mini_24c804c48a5838fd__to__claude-haiku-4-5` · semantic key `2b091c1ca66e729f278a53701c71f64d` · category `extract` · out tokens 6→10

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the contract end date as an ISO date: 'The agreement runs through 31 December 2026 with auto-renewal.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
2026-12-31
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
2026-12-31
```

</details>

### 13. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_25341ba9631034ad` → `migration__openai_gpt-4o-mini_25341ba9631034ad__to__claude-haiku-4-5` · semantic key `7619e5eb23b72f65092718fb8f19fa9a` · category `rewrite` · out tokens 8→13

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.97 — sequence similarity 0.97 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Remove the filler words: 'So basically we just kind of need to actually finalize the budget like today.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
We need to finalize the budget today.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
"We need to finalize the budget today."
```

</details>

### 14. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_253db1d8eda9896f` → `migration__openai_gpt-4o-mini_253db1d8eda9896f__to__claude-haiku-4-5` · semantic key `86cf23d8ce313332b06ef5f11e57654a` · category `rewrite` · out tokens 12→18

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Normalize this address into one line with proper capitalization: 'lagerstrasse 12 20095 hamburg germany'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Lagerstraße 12, 20095 Hamburg, Germany
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Lagerstrasse 12, 20095 Hamburg, Germany
```

</details>

### 15. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_26aa18bfc0c746c4` → `migration__openai_gpt-4o-mini_26aa18bfc0c746c4__to__claude-haiku-4-5` · semantic key `a365ddd6021a264d636ebbc6bc9d6f99` · category `rewrite` · out tokens 20→33

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.52 — sequence similarity 0.52 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Turn this into a polite decline: 'No, we won't build that feature.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
"Thank you for your suggestion, but we will not be proceeding with that feature at this time."
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Thank you for the suggestion. Unfortunately, we're unable to prioritize this feature at this time, but we appreciate you bringing it to our attention.
```

</details>

### 16. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_2744ecabaeb33f82` → `migration__openai_gpt-4o-mini_2744ecabaeb33f82__to__claude-haiku-4-5` · semantic key `0d56c24d9df924f8900098b1b4364680` · category `extract` · out tokens 23→30

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {temperature_c, sensor}: 'Sensor 7 in the cold room reads -18.5 degrees Celsius.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
{
  "temperature_c": -18.5,
  "sensor": 7
}
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
{
  "temperature_c": -18.5,
  "sensor": 7
}
```
````

</details>

### 17. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_2d57a74d193ceb50` → `migration__openai_gpt-4o-mini_2d57a74d193ceb50__to__claude-haiku-4-5` · semantic key `424b1baad00a1f8a3322a68babc8dd44` · category `rewrite` · out tokens 25→24

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.98 — sequence similarity 0.98 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Replace all personal data with [REDACTED]: 'Contact Anna Larsen at +45 22 11 33 44 or anna@example.dk for access.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
'Contact [REDACTED] at [REDACTED] or [REDACTED] for access.'
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Contact [REDACTED] at [REDACTED] or [REDACTED] for access.
```

</details>

### 18. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_30aaa018934ab03f` → `migration__openai_gpt-4o-mini_30aaa018934ab03f__to__claude-haiku-4-5` · semantic key `3292ede2593ef0084e15240dd35efd25` · category `rewrite` · out tokens 15→19

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.91 — sequence similarity 0.91 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Rewrite as a single bullet point: 'The meeting covered the hiring plan, the office move, and the holiday schedule.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
- The meeting addressed the hiring plan, office move, and holiday schedule.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
• The meeting addressed the hiring plan, office relocation, and holiday schedule.
```

</details>

### 19. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_32756b2ec547c216` → `migration__openai_gpt-4o-mini_32756b2ec547c216__to__claude-haiku-4-5` · semantic key `f115c3352607051cc642f1b500c365bc` · category `extract` · out tokens 16→31

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.93 — sequence similarity 0.93 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {sku, quantity}: 'Please ship 12 units of SKU-44821 to the Hamburg warehouse.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
{"sku":"SKU-44821","quantity":12}
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
{
  "sku": "SKU-44821",
  "quantity": 12
}
```
````

</details>

### 20. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_34bb8da117f20b0e` → `migration__openai_gpt-4o-mini_34bb8da117f20b0e__to__claude-haiku-4-5` · semantic key `3523f856a0e4f4307b89d206adc240ab` · category `extract` · out tokens 16→11

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.90 — sequence similarity 0.90 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the IBAN: 'Please wire the deposit to IBAN DE89 3704 0044 0532 0130 00 by Friday.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
DE89 3704 0044 0532 0130 00
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
DE89370400440532013000
```

</details>

### 21. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_37d5392016c26bcf` → `migration__openai_gpt-4o-mini_37d5392016c26bcf__to__claude-haiku-4-5` · semantic key `014d3b6bef5d2295c99480cd61a3d3fa` · category `classify` · out tokens 1→6

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.10 — sequence similarity 0.10 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Route this support ticket (billing/technical/account/shipping): 'I can't reset my password.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Technical
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**account**
```

</details>

### 22. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_39c0d06de1f8b940` → `migration__openai_gpt-4o-mini_39c0d06de1f8b940__to__claude-haiku-4-5` · semantic key `c8064709cfc5372f50f9983ffe382dc5` · category `classify` · out tokens 3→23

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.16 — sequence similarity 0.16 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Spam or not spam: 'Hi Sam, can we move our 2pm meeting to 3pm tomorrow?'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Not spam.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Not spam.

This is a legitimate personal or professional communication requesting to reschedule a meeting.
```

</details>

### 23. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_3d25d5ef9bc6a08a` → `migration__openai_gpt-4o-mini_3d25d5ef9bc6a08a__to__claude-haiku-4-5` · semantic key `567604ac5581ce8758b2be9a66bf756d` · category `classify` · out tokens 3→37

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.19 — sequence similarity 0.19 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Intent (question/complaint/praise/refund_request): 'The blender stopped working after two uses. I want my money back.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Refund request.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Intent: Refund Request**

**Reason:** Customer is requesting a refund due to a defective product (blender stopped working after minimal use).
```

</details>

### 24. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_412d29f5627ab5da` → `migration__openai_gpt-4o-mini_412d29f5627ab5da__to__claude-haiku-4-5` · semantic key `10abbf2dfe3a974a3bc832bf33540208` · category `classify` · out tokens 1→4

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Language of this text (ISO 639-1 code only): '¿Dónde está la estación de tren?'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
es
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
es
```

</details>

### 25. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_434e72fafcaf8ad7` → `migration__openai_gpt-4o-mini_434e72fafcaf8ad7__to__claude-haiku-4-5` · semantic key `f737891cd44b854a81e637847b016826` · category `extract` · out tokens 22→29

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {flight, gate}: 'Flight UA287 is now boarding at gate B14.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
{
  "flight": "UA287",
  "gate": "B14"
}
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
{
  "flight": "UA287",
  "gate": "B14"
}
```
````

</details>

### 26. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_43a46c2898a7ac58` → `migration__openai_gpt-4o-mini_43a46c2898a7ac58__to__claude-haiku-4-5` · semantic key `2ba2e95c8a199d9e9d4582cb0f381f4b` · category `classify` · out tokens 3→29

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.24 — sequence similarity 0.24 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Topic (billing/bug/feature_request/how_to): 'It would be great if exports supported CSV.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Feature Request.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Topic: feature_request**

This is a request for new functionality (CSV export support) that doesn't currently exist.
```

</details>

### 27. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_43b5d4942e1dbb79` → `migration__openai_gpt-4o-mini_43b5d4942e1dbb79__to__claude-haiku-4-5` · semantic key `d06b7828215d1d402bb38e045ddc029b` · category `classify` · out tokens 2→54

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.05 — sequence similarity 0.05 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Spam or not spam: 'Congratulations! You won a $1000 gift card, click here to claim.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Spam.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Spam**

Common spam indicators:
- Unsolicited congratulations/prize claim
- Urgency ("click here")
- Too-good-to-be-true offer
- Typical phishing/scam template
```

</details>

### 28. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_448da0337efb9d3e` → `migration__openai_gpt-4o-mini_448da0337efb9d3e__to__claude-haiku-4-5` · semantic key `da5041d97129f702041affb643acd8fc` · category `summarize` · out tokens 24→30

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.71 — sequence similarity 0.71 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Summarize this review in one sentence: 'I have used this laptop for three months. The screen is gorgeous and battery life is solid, but the fan noise under load is noticeable and the webcam is mediocre.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
The laptop has a beautiful screen and good battery life, but it has noticeable fan noise under load and a mediocre webcam.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
The laptop has an excellent display and battery life, but is hindered by loud fan noise under load and a subpar webcam.
```

</details>

### 29. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_45756453e5e98b19` → `migration__openai_gpt-4o-mini_45756453e5e98b19__to__claude-haiku-4-5` · semantic key `1c8a85694c69c00ea9cfb64ade4bbec6` · category `summarize` · out tokens 34→31

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.61 — sequence similarity 0.61 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] One-sentence executive summary: 'Q2 churn rose from 4% to 6%, driven by small-business accounts citing price increases; enterprise retention stayed flat while expansion revenue grew 9%.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Q2 churn increased from 4% to 6% due to price hikes impacting small-business accounts, while enterprise retention remained stable and expansion revenue increased by 9%.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Q2 churn doubled among small-business customers due to price increases, though enterprise accounts remained stable and expansion revenue grew 9%.
```

</details>

### 30. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_46a12c785e149290` → `migration__openai_gpt-4o-mini_46a12c785e149290__to__claude-haiku-4-5` · semantic key `bf68eae9aae83c9e123057b8b530d8f0` · category `extract` · out tokens 7→11

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the invoice number: 'Re: outstanding payment for invoice INV-2026-0457.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
INV-2026-0457
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
INV-2026-0457
```

</details>

### 31. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_499c03e5bb393348` → `migration__openai_gpt-4o-mini_499c03e5bb393348__to__claude-haiku-4-5` · semantic key `f938b325ffa0223e123e16ee8fc8f93b` · category `extract` · out tokens 21→36

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.98 — sequence similarity 0.98 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract all URLs as a JSON array: 'Docs moved to https://docs.example.com/v2; old links via http://example.com/legacy redirect.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
["https://docs.example.com/v2", "http://example.com/legacy"]
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
[
  "https://docs.example.com/v2",
  "http://example.com/legacy"
]
```
````

</details>

### 32. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_508d047cade5d1a6` → `migration__openai_gpt-4o-mini_508d047cade5d1a6__to__claude-haiku-4-5` · semantic key `b52db60497916ee283c01911dd51152a` · category `classify` · out tokens 3→86

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.08 — sequence similarity 0.08 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Priority (low/medium/high/urgent): 'Checkout intermittently fails for about 10% of customers.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Priority: High
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Priority: HIGH**

**Justification:**
- Direct revenue impact (10% of transactions failing)
- Customer-facing critical feature
- Affects purchasing capability
- High business cost despite "intermittent" nature

**Note:** Could escalate to URGENT if:
- Peak traffic period
- High-value customers affected
- Failure rate increasing
- Duration already extended
```

</details>

### 33. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_523ccefa131e4504` → `migration__openai_gpt-4o-mini_523ccefa131e4504__to__claude-haiku-4-5` · semantic key `fd44e8a30eb91976ca326ba857ec7051` · category `extract` · out tokens 22→29

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {from, to} airport codes: 'Searching flights CPH to JFK for two adults.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
{
  "from": "CPH",
  "to": "JFK"
}
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
{
  "from": "CPH",
  "to": "JFK"
}
```
````

</details>

### 34. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_54c3d8c3eaa5f242` → `migration__openai_gpt-4o-mini_54c3d8c3eaa5f242__to__claude-haiku-4-5` · semantic key `516f23ff5337e8917978748cf61ca003` · category `extract` · out tokens 33→55

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.98 — sequence similarity 0.98 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {city, country}: 'Our HQ is in Lyon, France, with a satellite office in Austin.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
[
    {"city": "Lyon", "country": "France"},
    {"city": "Austin", "country": "USA"}
]
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
[
  {
    "city": "Lyon",
    "country": "France"
  },
  {
    "city": "Austin",
    "country": "USA"
  }
]
```
````

</details>

### 35. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_58b57d43a9724fed` → `migration__openai_gpt-4o-mini_58b57d43a9724fed__to__claude-haiku-4-5` · semantic key `d7053f5a52ee1b57c4304d2a46fe3c31` · category `summarize` · out tokens 20→25

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.46 — sequence similarity 0.46 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Summarize the risk in one sentence: 'While the merger promises cost savings through shared infrastructure, analysts warn that cultural integration and overlapping product lines pose execution risks.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
The merger's anticipated cost savings may be jeopardized by challenges in cultural integration and overlapping product lines.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
The merger's execution risks stem from cultural integration challenges and product line overlap that could undermine projected cost savings.
```

</details>

### 36. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_5ae4f7a6438490f1` → `migration__openai_gpt-4o-mini_5ae4f7a6438490f1__to__claude-haiku-4-5` · semantic key `e916f9f65a95570c94a718bf3b0d8280` · category `classify` · out tokens 2→4

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.86 — sequence similarity 0.86 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Does this text contain personal data? (yes/no): 'My SSN is 523-12-9876, please update my file.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Yes.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Yes
```

</details>

### 37. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_5f462a6b9a1687df` → `migration__openai_gpt-4o-mini_5f462a6b9a1687df__to__claude-haiku-4-5` · semantic key `af3c1e4a0f97c0e63c2a08a2d25b389b` · category `translate` · out tokens 10→18

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Translate to Dutch: 'Your invoice is attached as a PDF.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
'Uw factuur is als PDF bijgevoegd.'
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
'Uw factuur is als PDF bijgevoegd.'
```

</details>

### 38. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_6250aff19d9ec734` → `migration__openai_gpt-4o-mini_6250aff19d9ec734__to__claude-haiku-4-5` · semantic key `316bee833c904971f79dde46cd5f8b7e` · category `extract` · out tokens 20→24

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract all dates as a JSON array of ISO dates: 'The invoice was issued 2026-03-01 and is due 2026-03-15.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
["2026-03-01", "2026-03-15"]
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
["2026-03-01", "2026-03-15"]
```
````

</details>

### 39. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_65084dc52867761c` → `migration__openai_gpt-4o-mini_65084dc52867761c__to__claude-haiku-4-5` · semantic key `cce3a82477aa856bb215ef92d3f6989e` · category `rewrite` · out tokens 16→22

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.66 — sequence similarity 0.66 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Neutralize the tone for a status update: 'The vendor STILL has not fixed their broken API after three weeks of us begging.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
The vendor has not yet resolved the API issue after three weeks of follow-up.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
"The vendor's API issue remains unresolved after three weeks of follow-up requests."
```

</details>

### 40. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_65611a177f7b1b6d` → `migration__openai_gpt-4o-mini_65611a177f7b1b6d__to__claude-haiku-4-5` · semantic key `d5a579533a43864af13676b471903e98` · category `summarize` · out tokens 22→37

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.76 — sequence similarity 0.76 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Condense this email to one sentence: 'Following up on our call - attached is the revised proposal with updated timelines, a 5% volume discount as discussed, and the security questionnaire your IT team requested.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Attached is the revised proposal with updated timelines, a 5% volume discount, and the requested security questionnaire.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Following up on our call, I've attached the revised proposal with updated timelines, a 5% volume discount, and the security questionnaire your IT team requested.
```

</details>

### 41. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_69a66c3ebce30c3a` → `migration__openai_gpt-4o-mini_69a66c3ebce30c3a__to__claude-haiku-4-5` · semantic key `c8437a70cc226f4269e81d6e5376ae31` · category `classify` · out tokens 2→106

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.00 — sequence similarity 0.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Churn risk (low/medium/high): 'We're evaluating alternatives because prices went up again.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Medium.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Churn risk: HIGH**

**Key indicators:**
- Explicit evaluation of competitors ("evaluating alternatives")
- Price sensitivity as primary driver
- Recurring frustration ("went up again" implies multiple increases)
- Active consideration stage, not just complaint

**Recommended actions:**
- Immediate outreach with retention offer
- Review pricing/contract terms for optimization
- Propose value-add alternatives to offset cost increase
- Escalate to retention specialist or account manager
```

</details>

### 42. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_6b168e24385da353` → `migration__openai_gpt-4o-mini_6b168e24385da353__to__claude-haiku-4-5` · semantic key `0c4edece41bf1d899953f44b0300c8a9` · category `summarize` · out tokens 28→36

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.74 — sequence similarity 0.74 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Summarize the incident impact in one sentence: 'The pricing bug showed VAT-exclusive totals to EU customers for six hours; 214 orders were affected and will be refunded the difference automatically.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
The pricing bug impacted 214 EU orders by displaying VAT-exclusive totals for six hours, and affected customers will receive automatic refunds for the difference.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
A pricing bug displayed incorrect VAT-exclusive totals to EU customers for six hours, affecting 214 orders that will receive automatic refunds for the difference.
```

</details>

### 43. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_6ea12ea90c084412` → `migration__openai_gpt-4o-mini_6ea12ea90c084412__to__claude-haiku-4-5` · semantic key `210a79a200bb7dcd008914f29c333738` · category `translate` · out tokens 19→27

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.97 — sequence similarity 0.97 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Translate to Swedish: 'Your payment could not be processed. Please check your card details.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
"Ditt betalning kunde inte behandlas. Vänligen kontrollera dina kortuppgifter."
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Din betalning kunde inte behandlas. Vänligen kontrollera dina kortuppgifter.
```

</details>

### 44. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_6ec19ca40a42f00e` → `migration__openai_gpt-4o-mini_6ec19ca40a42f00e__to__claude-haiku-4-5` · semantic key `0303608cebbc1a9f026c53d106987d25` · category `extract` · out tokens 8→12

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the tracking number: 'Your parcel 1Z999AA10123456784 left our facility this morning.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
1Z999AA10123456784
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
1Z999AA10123456784
```

</details>

### 45. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_6fcb15dcf7297dd6` → `migration__openai_gpt-4o-mini_6fcb15dcf7297dd6__to__claude-haiku-4-5` · semantic key `81fd0727c6c99b8a72958ae7ea0d9eeb` · category `extract` · out tokens 2→6

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the last four card digits: 'The charge went to the Visa ending in 4242.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
4242
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
4242
```

</details>

### 46. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_719d4d1be2fdf365` → `migration__openai_gpt-4o-mini_719d4d1be2fdf365__to__claude-haiku-4-5` · semantic key `95064c205282f4218605fc238b7a16c7` · category `classify` · out tokens 1→25

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.10 — sequence similarity 0.10 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Intent (question/complaint/praise/refund_request): 'Your support team solved my issue in minutes!'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Praise
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Intent: Praise**

The customer is expressing satisfaction with the support team's quick and effective resolution.
```

</details>

### 47. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_74e55da373fc0e6d` → `migration__openai_gpt-4o-mini_74e55da373fc0e6d__to__claude-haiku-4-5` · semantic key `f2dc429e9557c4ad73e2f02c404bf2bd` · category `extract` · out tokens 19→36

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.98 — sequence similarity 0.98 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {name, company}: 'Hi, this is Maria Gonzalez calling from Acme Robotics about the Q3 contract.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
{"name": "Maria Gonzalez", "company": "Acme Robotics"}
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
{
  "name": "Maria Gonzalez",
  "company": "Acme Robotics"
}
```
````

</details>

### 48. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_783e9d41ed03ffc2` → `migration__openai_gpt-4o-mini_783e9d41ed03ffc2__to__claude-haiku-4-5` · semantic key `a3fd53885f3b2ddb7055dce2de11f611` · category `summarize` · out tokens 20→34

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.38 — sequence similarity 0.38 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Summarize this support thread in one sentence: 'Customer reported login failures on mobile, support suggested clearing the cache which did not help, the issue was escalated to engineering who found an expired certificate, a fix was deployed, and the customer confirmed resolution.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
A customer experienced login failures on mobile, which were resolved after engineering identified and fixed an expired certificate.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
A customer's mobile login failures caused by an expired certificate were resolved after support escalated to engineering, deployed a fix, and confirmed the issue was fixed.
```

</details>

### 49. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_7dff935818428c9d` → `migration__openai_gpt-4o-mini_7dff935818428c9d__to__claude-haiku-4-5` · semantic key `7c6853ae24d2c12058dc8aca810a418d` · category `classify` · out tokens 3→44

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.13 — sequence similarity 0.13 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Priority (low/medium/high/urgent): 'A tooltip on the settings page has a small typo.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Priority: Low
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Priority: Low**

A tooltip typo is a minor cosmetic issue with no impact on functionality, user safety, or core experience. It can be addressed in a routine update or maintenance cycle.
```

</details>

### 50. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_7ffafe03a6e870e1` → `migration__openai_gpt-4o-mini_7ffafe03a6e870e1__to__claude-haiku-4-5` · semantic key `5718b93beb73ba62cda56c5aa27cf754` · category `rewrite` · out tokens 7→18

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.43 — sequence similarity 0.43 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Make this subject line professional: 'wanna chat about the budget thing'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
"Request to Discuss Budget Matters"
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
"Budget Discussion Request"

or

"Meeting Request: Budget Review"
```

</details>

### 51. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_83c11dfa94acba92` → `migration__openai_gpt-4o-mini_83c11dfa94acba92__to__claude-haiku-4-5` · semantic key `041ce06dc072980247a446b3c8e053f6` · category `extract` · out tokens 19→35

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.97 — sequence similarity 0.97 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {product, issue}: 'The X200 vacuum's battery drains within ten minutes.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
{"product":"X200 vacuum","issue":"battery drains within ten minutes"}
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
{
  "product": "X200 vacuum",
  "issue": "battery drains within ten minutes"
}
```
````

</details>

### 52. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_87364859ab450ba8` → `migration__openai_gpt-4o-mini_87364859ab450ba8__to__claude-haiku-4-5` · semantic key `45006f1a59cb08823272797ddaeded5e` · category `rewrite` · out tokens 15→24

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.50 — sequence similarity 0.50 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Rewrite for a non-technical audience: 'The outage was caused by an expired TLS certificate on the load balancer.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
The outage happened because the security certificate on the load balancer had expired.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
The website went down because a security credential that protects your connection expired and wasn't renewed in time.
```

</details>

### 53. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_87a2d2cadaf4c963` → `migration__openai_gpt-4o-mini_87a2d2cadaf4c963__to__claude-haiku-4-5` · semantic key `5ce47fc287f6dfc62f171b1f7e4c1337` · category `translate` · out tokens 24→29

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.91 — sequence similarity 0.91 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Translate to Polish: 'Two-factor authentication is now enabled on your account.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
"Uwierzytelnianie dwuetapowe jest teraz włączone na Twoim koncie."
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Uwierzytelnianie dwuskładnikowe jest teraz włączone na Twoim koncie.
```

</details>

### 54. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_8fdd43b2804e3bf4` → `migration__openai_gpt-4o-mini_8fdd43b2804e3bf4__to__claude-haiku-4-5` · semantic key `734729cc5c15e0d0fbe088a85bc56859` · category `extract` · out tokens 3→11

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.50 — sequence similarity 0.50 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the order number: 'Hello, I'm writing about order #84412-B which arrived damaged.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
84412-B
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Order number: 84412-B
```

</details>

### 55. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_91e3187c78aa9a93` → `migration__openai_gpt-4o-mini_91e3187c78aa9a93__to__claude-haiku-4-5` · semantic key `027bfa9a19cdee5b43841a6771753a21` · category `classify` · out tokens 2→64

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.00 — sequence similarity 0.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Spam or not spam: 'URGENT: verify your account within 24 hours or it will be suspended.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Spam.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Spam** (phishing attempt)

Characteristics:
- Artificial urgency ("URGENT", "24 hours")
- Threat of account suspension
- Requests verification (typical phishing tactic)
- Legitimate companies rarely use this approach via unsolicited messages
```

</details>

### 56. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_94a3f6772bacae93` → `migration__openai_gpt-4o-mini_94a3f6772bacae93__to__claude-haiku-4-5` · semantic key `f1aa6e9b63b41fbdb172c2c55c347cef` · category `rewrite` · out tokens 10→14

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.70 — sequence similarity 0.70 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Make this concise (max 10 words): 'Due to the fact that it was raining, we made the decision to postpone the event.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
We decided to postpone the event due to rain.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
We postponed the event because it was raining.
```

</details>

### 57. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_955f7779ae173fb8` → `migration__openai_gpt-4o-mini_955f7779ae173fb8__to__claude-haiku-4-5` · semantic key `09c2128b8b973819cea35b8af9090efb` · category `extract` · out tokens 34→42

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {street, zip, city}: 'Send returns to Lagerstrasse 12, 20095 Hamburg, attention Returns Dept.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
{
  "street": "Lagerstrasse 12",
  "zip": "20095",
  "city": "Hamburg"
}
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
{
  "street": "Lagerstrasse 12",
  "zip": "20095",
  "city": "Hamburg"
}
```
````

</details>

### 58. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_971ceef22d00b451` → `migration__openai_gpt-4o-mini_971ceef22d00b451__to__claude-haiku-4-5` · semantic key `5bf36323c5f6371744833313a4747986` · category `classify` · out tokens 2→47

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.06 — sequence similarity 0.06 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Sentiment (positive/negative/neutral): 'It's fine. Does the job, nothing special.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Neutral.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Neutral

The statement expresses acceptance and basic satisfaction without enthusiasm or criticism. The phrase "does the job" is functional/utilitarian, and "nothing special" explicitly indicates lack of strong positive or negative emotion.
```

</details>

### 59. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_98c2009111708bc5` → `migration__openai_gpt-4o-mini_98c2009111708bc5__to__claude-haiku-4-5` · semantic key `bc910dc8c143cf570a6cd37babc47b39` · category `summarize` · out tokens 9→19

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.64 — sequence similarity 0.64 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Headline (max 8 words) for this update: 'The mobile app now supports offline mode, letting field technicians complete inspections without connectivity and sync automatically once back online.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
"Mobile App Now Supports Offline Inspection Mode"
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Mobile App Gains Offline Inspection Capability, Auto-Syncs
```

</details>

### 60. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_9ad3271e2ca360d8` → `migration__openai_gpt-4o-mini_9ad3271e2ca360d8__to__claude-haiku-4-5` · semantic key `e2ab3a1b05ca5834dc13f15cf52ed565` · category `classify` · out tokens 20→42

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.42 — sequence similarity 0.42 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Topic (billing/bug/feature_request/how_to): 'The dashboard shows a 500 error when filtering by date.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Topic: Bug  
Description: The dashboard displays a 500 error when attempting to filter by date.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Topic: Bug**

This is a technical malfunction where the dashboard fails to process a date filter request, resulting in a server error (500). It should be reported as a bug.
```

</details>

### 61. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_9be737b38dbda877` → `migration__openai_gpt-4o-mini_9be737b38dbda877__to__claude-haiku-4-5` · semantic key `04695fb1022b033eff5e25885bfd1148` · category `rewrite` · out tokens 6→9

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Rewrite in active voice: 'The proposal was reviewed by the committee.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
The committee reviewed the proposal.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
The committee reviewed the proposal.
```

</details>

### 62. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_9c845e2be1b1e49c` → `migration__openai_gpt-4o-mini_9c845e2be1b1e49c__to__claude-haiku-4-5` · semantic key `a92c84c6bbaf5d5310f6338dad751ac1` · category `translate` · out tokens 15→24

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.99 — sequence similarity 0.99 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Translate to Spanish: 'Click the link below to reset your password.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
'Haz clic en el enlace a continuación para restablecer tu contraseña.'
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Haz clic en el enlace a continuación para restablecer tu contraseña.
```

</details>

### 63. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_9efaa6d91c5ae0ef` → `migration__openai_gpt-4o-mini_9efaa6d91c5ae0ef__to__claude-haiku-4-5` · semantic key `10fe30a771f2aa63d1baba05b39ca5ad` · category `classify` · out tokens 2→4

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.80 — sequence similarity 0.80 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Does this text contain personal data? (yes/no): 'Bad weather in the region delayed all shipments.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
No.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
No
```

</details>

### 64. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_9f9b8b6492ceb730` → `migration__openai_gpt-4o-mini_9f9b8b6492ceb730__to__claude-haiku-4-5` · semantic key `7f6bf478b47d137f4448ac49049f8af3` · category `translate` · out tokens 10→14

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.97 — sequence similarity 0.97 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Translate to Italian: 'The item is currently out of stock.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
"L'articolo è attualmente esaurito."
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
L'articolo è attualmente esaurito.
```

</details>

### 65. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_a3d475c0b7113ad0` → `migration__openai_gpt-4o-mini_a3d475c0b7113ad0__to__claude-haiku-4-5` · semantic key `ee913aa9fe18c7fb150dcd41b5c2c203` · category `extract` · out tokens 13→26

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.70 — sequence similarity 0.70 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract all monetary amounts as a JSON array: 'Setup costs $500, then $99 per month, plus a $25 activation fee.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
[500, 99, 25]
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
[
  "$500",
  "$99",
  "$25"
]
```
````

</details>

### 66. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_a41653955a425c0c` → `migration__openai_gpt-4o-mini_a41653955a425c0c__to__claude-haiku-4-5` · semantic key `949a8d237ab83a85ad159a27bbcde40f` · category `rewrite` · out tokens 14→33

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.44 — sequence similarity 0.44 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Soften this for a performance review: 'Your code is sloppy and full of bugs.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
"There's an opportunity to improve the clarity and stability of your code."
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
"There are opportunities to improve code quality and reduce defects. I'd recommend focusing on code review processes and testing coverage to help catch issues earlier."
```

</details>

### 67. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_ab851fea5c59373c` → `migration__openai_gpt-4o-mini_ab851fea5c59373c__to__claude-haiku-4-5` · semantic key `615c493376abe9f341e270e4334d5f15` · category `translate` · out tokens 19→56

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.52 — sequence similarity 0.52 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Translate to German: 'Your order has been shipped and will arrive in 3-5 business days.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
„Ihre Bestellung wurde versendet und wird in 3-5 Werktagen ankommen.“
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Deine Bestellung wurde versandt und kommt in 3-5 Werktagen an.

(Or more formally: Ihre Bestellung wurde versandt und kommt in 3-5 Werktagen an.)
```

</details>

### 68. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_ad012191d039df98` → `migration__openai_gpt-4o-mini_ad012191d039df98__to__claude-haiku-4-5` · semantic key `11e62c1a67cf27d0973fbc2c8db89372` · category `extract` · out tokens 5→9

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.92 — sequence similarity 0.92 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the version number: 'After updating to v2.14.3 the export button disappeared.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
2.14.3
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
v2.14.3
```

</details>

### 69. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_b3f458c2b6df3b54` → `migration__openai_gpt-4o-mini_b3f458c2b6df3b54__to__claude-haiku-4-5` · semantic key `60e336e5124e808d78aac9cc75c5fee9` · category `summarize` · out tokens 19→22

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.47 — sequence similarity 0.47 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] One-line summary of this changelog: 'Fixed a memory leak in the upload handler, improved dark-mode contrast, added keyboard shortcuts, deprecated the legacy export format.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Fixed memory leak, improved dark-mode contrast, added keyboard shortcuts, and deprecated legacy export format.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Fixed memory leak and deprecated legacy export format while adding keyboard shortcuts and improving dark-mode contrast.
```

</details>

### 70. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_b6c494b97849854e` → `migration__openai_gpt-4o-mini_b6c494b97849854e__to__claude-haiku-4-5` · semantic key `2318178fff07c05cf38515b57b811c0b` · category `extract` · out tokens 66→91

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.90 — sequence similarity 0.90 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the action items as a JSON array: 'John will email the report, Lisa books the venue, and we all review the deck by Friday.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
[
    {
        "person": "John",
        "action": "email the report"
    },
    {
        "person": "Lisa",
        "action": "book the venue"
    },
    {
        "action": "review the deck",
        "deadline": "Friday"
    }
]
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
[
  {
    "owner": "John",
    "action": "email the report"
  },
  {
    "owner": "Lisa",
    "action": "book the venue"
  },
  {
    "owner": "everyone",
    "action": "review the deck",
    "deadline": "Friday"
  }
]
```
````

</details>

### 71. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_b8ce3b39b00161b1` → `migration__openai_gpt-4o-mini_b8ce3b39b00161b1__to__claude-haiku-4-5` · semantic key `41ce107a1affe05e6b17565294ca3cad` · category `translate` · out tokens 11→21

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.93 — sequence similarity 0.93 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Translate to French: 'Your subscription will renew on July 1st.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Votre abonnement sera renouvelé le 1er juillet.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Votre abonnement se renouvellera le 1er juillet.
```

</details>

### 72. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_b8d7a232e7ca0e92` → `migration__openai_gpt-4o-mini_b8d7a232e7ca0e92__to__claude-haiku-4-5` · semantic key `e0bef6f55d991d1bb48c1f9493565f38` · category `summarize` · out tokens 34→42

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.63 — sequence similarity 0.63 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] TL;DR of these meeting notes in one sentence: 'We agreed to ship the beta on June 20, Maria owns the migration guide, the pricing review moved to next week, and we revisit the SLA discussion after the customer call.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Beta ships on June 20, Maria is responsible for the migration guide, pricing review postponed to next week, and SLA discussion will be revisited after the customer call.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
The team set a June 20 beta launch date with Maria responsible for the migration guide, postponed the pricing review to next week, and will address SLA concerns following a customer call.
```

</details>

### 73. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_bd598f1d9a3990c3` → `migration__openai_gpt-4o-mini_bd598f1d9a3990c3__to__claude-haiku-4-5` · semantic key `335e2d3d7f50c1c0465f7c74334f4813` · category `summarize` · out tokens 39→35

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.46 — sequence similarity 0.46 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Summarize in one sentence for a status page: 'Between 09:12 and 10:47 UTC some API requests returned elevated 5xx errors due to a failed database failover; traffic was rerouted and error rates returned to normal.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
API requests experienced elevated 5xx errors between 09:12 and 10:47 UTC due to a failed database failover, but traffic was rerouted and error rates have since normalized.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Between 09:12 and 10:47 UTC, a database failover failure caused elevated API errors that were resolved after traffic rerouting.
```

</details>

### 74. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_bf4cf18052faa0ad` → `migration__openai_gpt-4o-mini_bf4cf18052faa0ad__to__claude-haiku-4-5` · semantic key `4ccf03628906ff9b4509f832b641196e` · category `classify` · out tokens 5→24

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.17 — sequence similarity 0.17 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Route this support ticket (billing/technical/account/shipping): 'How do I download my invoices for tax season?'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Route to: billing.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Account**

This request relates to accessing account documents and financial records, which falls under account management.
```

</details>

### 75. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_bffb56ac2e2afb97` → `migration__openai_gpt-4o-mini_bffb56ac2e2afb97__to__claude-haiku-4-5` · semantic key `33037829548715a2bf65a126b2d21129` · category `rewrite` · out tokens 15→35

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.70 — sequence similarity 0.70 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Rewrite politely for a customer email: 'Send me the report now.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Could you please send me the report at your earliest convenience? Thank you!
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
"Could you please send me the report at your earliest convenience?"

Or alternatively:

"Would you be able to send me the report? Thank you."
```

</details>

### 76. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_c40059f67e1e2cc4` → `migration__openai_gpt-4o-mini_c40059f67e1e2cc4__to__claude-haiku-4-5` · semantic key `44372a681f71cc109ed263885c6238c5` · category `extract` · out tokens 6→11

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.97 — sequence similarity 0.97 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the username: 'User @data_wrangler_88 reported the sync issue first.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
data_wrangler_88
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
@data_wrangler_88
```

</details>

### 77. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_c647a3c2f20c2816` → `migration__openai_gpt-4o-mini_c647a3c2f20c2816__to__claude-haiku-4-5` · semantic key `5ec30e41ddb3e338d99f0ad26f7b90ae` · category `extract` · out tokens 8→11

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the phone number: 'Call our support line at (415) 555-0132 between 9 and 5.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
(415) 555-0132
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
(415) 555-0132
```

</details>

### 78. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_c6f34a2dbb588911` → `migration__openai_gpt-4o-mini_c6f34a2dbb588911__to__claude-haiku-4-5` · semantic key `b34a1e8841bcfaa4226ea10d738a5154` · category `classify` · out tokens 2→31

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.13 — sequence similarity 0.13 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Sentiment (positive/negative/neutral): 'Third time my delivery is late. I want a refund.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Negative.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Negative**

The customer expresses frustration over repeated late deliveries and is requesting a refund, indicating dissatisfaction.
```

</details>

### 79. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_c9758760d9062a8a` → `migration__openai_gpt-4o-mini_c9758760d9062a8a__to__claude-haiku-4-5` · semantic key `65638ff5a5584c444f6079819e446940` · category `translate` · out tokens 16→22

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.91 — sequence similarity 0.91 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Translate to Norwegian: 'Your return has been received and your refund is on its way.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
"Din retur har blitt mottatt, og refusjonen din er på vei."
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
"Din retur er mottatt og refusjonen din er på vei."
```

</details>

### 80. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_cb5c227b4600c23b` → `migration__openai_gpt-4o-mini_cb5c227b4600c23b__to__claude-haiku-4-5` · semantic key `b9e5dd7efe0972527feafb3180c0882e` · category `extract` · out tokens 30→38

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {day, time, timezone}: 'Let's sync Thursday at 14:30 CET on the usual bridge.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
{
  "day": "Thursday",
  "time": "14:30",
  "timezone": "CET"
}
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
{
  "day": "Thursday",
  "time": "14:30",
  "timezone": "CET"
}
```
````

</details>

### 81. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_cc4244d85dcb02a8` → `migration__openai_gpt-4o-mini_cc4244d85dcb02a8__to__claude-haiku-4-5` · semantic key `d990c7a34fccab1f73a9ab0c3bd02ffd` · category `rewrite` · out tokens 11→34

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.60 — sequence similarity 0.60 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Make this more formal: 'Hey, can you take a look at this when you get a sec?'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
"Could you please review this at your earliest convenience?"
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
"Could you please review this at your earliest convenience?"

Or, alternatively:

"Would you be able to examine this when you have a moment?"
```

</details>

### 82. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_d05e25bc18b05250` → `migration__openai_gpt-4o-mini_d05e25bc18b05250__to__claude-haiku-4-5` · semantic key `3eb7add5b3f1726b54d85cfebd6f6ffa` · category `translate` · out tokens 16→24

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.88 — sequence similarity 0.88 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Translate to Danish: 'Thank you for contacting support. We will reply within 24 hours.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Tak for at kontakte support. Vi vil svare inden for 24 timer.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
"Tak fordi du kontaktede support. Vi svarer inden for 24 timer."
```

</details>

### 83. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_d08713e52b495d5f` → `migration__openai_gpt-4o-mini_d08713e52b495d5f__to__claude-haiku-4-5` · semantic key `c073f1bc0de9ceee4df90d02e169d104` · category `classify` · out tokens 1→39

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.03 — sequence similarity 0.03 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Churn risk (low/medium/high): 'Renewed for another year, the new features are great.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Low
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Low**

The statement indicates customer satisfaction with the product (praising new features) and commitment (renewed contract), both of which are strong indicators of low churn risk.
```

</details>

### 84. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_d12f21f7c0897035` → `migration__openai_gpt-4o-mini_d12f21f7c0897035__to__claude-haiku-4-5` · semantic key `521e3f6046a6e48ca081bf098a8f1c68` · category `classify` · out tokens 1→9

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.56 — sequence similarity 0.56 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Route this support ticket (billing/technical/account/shipping): 'I was charged twice this month.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Billing
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Route: Billing**
```

</details>

### 85. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_d291c95881afa86c` → `migration__openai_gpt-4o-mini_d291c95881afa86c__to__claude-haiku-4-5` · semantic key `8b502f8bf0aee382d2d5df6024796695` · category `extract` · out tokens 6→10

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the license plate: 'The delivery van, plate HH-AB 1234, was parked at dock 3.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
HH-AB 1234
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
HH-AB 1234
```

</details>

### 86. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_d45209a8ac32b01b` → `migration__openai_gpt-4o-mini_d45209a8ac32b01b__to__claude-haiku-4-5` · semantic key `bd5b6d0c2159ea4a41556d0be8838e9f` · category `extract` · out tokens 25→33

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract as JSON {employee_id, department}: 'Badge E-20331 belongs to Priya Nair in Procurement.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
{
  "employee_id": "E-20331",
  "department": "Procurement"
}
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
{
  "employee_id": "E-20331",
  "department": "Procurement"
}
```
````

</details>

### 87. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_d80e914e1872be3d` → `migration__openai_gpt-4o-mini_d80e914e1872be3d__to__claude-haiku-4-5` · semantic key `c84aa056273b4bbde705343b1d599ddd` · category `classify` · out tokens 4→123

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.06 — sequence similarity 0.06 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Priority (low/medium/high/urgent): 'Login is broken for all users in production.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Priority: Urgent
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Priority: URGENT**

This requires immediate action because:
- **Scope**: All users affected (not isolated)
- **Environment**: Production (live service)
- **Impact**: Complete service unavailability for authentication
- **Business risk**: Revenue loss, SLA violations, reputational damage

**Recommended immediate actions:**
1. Page on-call engineer/incident commander
2. Declare SEV-1 incident
3. Begin root cause investigation
4. Prepare status page communication
5. Activate war room if not already done
```

</details>

### 88. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_d8287451b625e968` → `migration__openai_gpt-4o-mini_d8287451b625e968__to__claude-haiku-4-5` · semantic key `8b2dbd7d26a1fa8899321deccac361f0` · category `summarize` · out tokens 30→31

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.93 — sequence similarity 0.93 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Summarize for a shift handover in one sentence: 'Night shift saw two failed batch jobs which were rerun successfully, disk usage on db-3 hit 85%, and the vendor confirmed the maintenance window for Saturday.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Night shift reported two failed batch jobs successfully rerun, disk usage on db-3 reached 85%, and the vendor confirmed Saturday's maintenance window.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Night shift reran two failed batch jobs successfully, disk usage on db-3 reached 85%, and vendor confirmed Saturday maintenance window.
```

</details>

### 89. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_d9d019d6590c4ea8` → `migration__openai_gpt-4o-mini_d9d019d6590c4ea8__to__claude-haiku-4-5` · semantic key `629a8cca6370942fa25d6a5b5b19c789` · category `classify` · out tokens 1→4

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.00 — sequence similarity 0.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Language of this text (ISO 639-1 code only): 'Hvor er nærmeste togstation?'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
da
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
no
```

</details>

### 90. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_dab2ba3fba1c2c28` → `migration__openai_gpt-4o-mini_dab2ba3fba1c2c28__to__claude-haiku-4-5` · semantic key `a9852fe03e6143801baea8c1d1cd5cd8` · category `classify` · out tokens 2→23

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.19 — sequence similarity 0.19 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Intent (question/complaint/praise/refund_request): 'Why is my order still not here after two weeks?'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Complaint.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Intent: Complaint**

The customer is expressing dissatisfaction about a delayed order delivery.
```

</details>

### 91. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_dd77043b1c7c8855` → `migration__openai_gpt-4o-mini_dd77043b1c7c8855__to__claude-haiku-4-5` · semantic key `e5f738403bdc9080bc6f9ff3683a7e56` · category `extract` · out tokens 16→23

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the names of all people mentioned as a JSON array: 'Tom and Aisha met with Dr. Keller to review the audit.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

````text
```json
["Tom", "Aisha", "Dr. Keller"]
```
````

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

````text
```json
["Tom", "Aisha", "Dr. Keller"]
```
````

</details>

### 92. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_e0084440d3367cc4` → `migration__openai_gpt-4o-mini_e0084440d3367cc4__to__claude-haiku-4-5` · semantic key `ef72cd51a90ab8b41807dd733ad60e26` · category `classify` · out tokens 3→48

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.01 — sequence similarity 0.01 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Moderation (allowed/flagged): 'You are an idiot and your product is garbage.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Flagged.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Flagged**

This contains insults and harsh criticism that violates respectful communication standards. The use of "idiot" is a personal attack, and "garbage" is inflammatory language intended to demean.
```

</details>

### 93. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_e3dba8cb7a343d25` → `migration__openai_gpt-4o-mini_e3dba8cb7a343d25__to__claude-haiku-4-5` · semantic key `66c94c4dbf01d113119e8189cf3351b3` · category `classify` · out tokens 1→4

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Language of this text (ISO 639-1 code only): 'Wo ist der nächste Bahnhof?'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
de
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
de
```

</details>

### 94. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_ee8e8bb716aaf7ba` → `migration__openai_gpt-4o-mini_ee8e8bb716aaf7ba__to__claude-haiku-4-5` · semantic key `fb1e148017a6803bf11d3d0a11582df0` · category `classify` · out tokens 1→29

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.12 — sequence similarity 0.12 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Route this support ticket (billing/technical/account/shipping): 'My package shows delivered but never arrived.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Shipping
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Route: Shipping**

This is a delivery/fulfillment issue that requires investigation by the shipping/logistics department.
```

</details>

### 95. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_f384498135f973b4` → `migration__openai_gpt-4o-mini_f384498135f973b4__to__claude-haiku-4-5` · semantic key `7ffc47d81d447c7d5d26ea88dd025549` · category `translate` · out tokens 12→20

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ✅ 0.88 — sequence similarity 0.88 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Translate to Portuguese: 'Free shipping on orders over 50 euros.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
'Frete grátis em pedidos acima de 50 euros.'
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Envio grátis em pedidos acima de 50 euros.
```

</details>

### 96. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_f3a3131603de8886` → `migration__openai_gpt-4o-mini_f3a3131603de8886__to__claude-haiku-4-5` · semantic key `c5e2753c8ca10d2e767dc6f412c0374a` · category `extract` · out tokens 9→14

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the email address: 'Reach me at jane.doe+work@example.co.uk anytime.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
jane.doe+work@example.co.uk
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
jane.doe+work@example.co.uk
```

</details>

### 97. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_f41ab2f346e89f25` → `migration__openai_gpt-4o-mini_f41ab2f346e89f25__to__claude-haiku-4-5` · semantic key `a667d9c535c9ce3e0efaf1a554b1cd2c` · category `summarize` · out tokens 39→39

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.47 — sequence similarity 0.47 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Summarize this bug report in one sentence: 'Steps: open the editor, paste a table from Excel, undo twice - the app freezes for about 30 seconds and sometimes loses the last paragraph; happens on Windows and macOS since v4.2.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
The app freezes for about 30 seconds and may lose the last paragraph when pasting a table from Excel and undoing twice, occurring on both Windows and macOS since v4.2.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Pasting an Excel table into the editor and undoing twice causes a 30-second freeze and potential paragraph loss on Windows and macOS in v4.2+.
```

</details>

### 98. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_f6d721aa5bd0e3a5` → `migration__openai_gpt-4o-mini_f6d721aa5bd0e3a5__to__claude-haiku-4-5` · semantic key `c95492de516adbc4eb55ea783419693b` · category `summarize` · out tokens 22→21

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.58 — sequence similarity 0.58 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Summarize the recurring feedback theme in one sentence: 'Across 80 survey responses, users repeatedly praised onboarding speed but flagged confusing invoice layouts and slow support response on weekends.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Users commend the fast onboarding process but consistently express dissatisfaction with the confusing invoice layouts and slow support response during weekends.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
Users value fast onboarding but struggle with confusing invoices and slow weekend support.
```

</details>

### 99. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_f7eeb1f8eccdaae3` → `migration__openai_gpt-4o-mini_f7eeb1f8eccdaae3__to__claude-haiku-4-5` · semantic key `dc2f19dd26fe70a632b84d09a9dc4b15` · category `extract` · out tokens 2→6

- **exact** ✅ 1.00 — normalized texts match
- **fuzzy** ✅ 1.00 — sequence similarity 1.00 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Extract the discount percentage: 'Use code SPRING for 15% off your first order.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
15%
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
15%
```

</details>

### 100. [system] You are a precise assistant. Answer directly and concisely. No preambl…

`openai_gpt-4o-mini_f7fe0e021a97d678` → `migration__openai_gpt-4o-mini_f7fe0e021a97d678__to__claude-haiku-4-5` · semantic key `ed3788822c7af6968f88bcb94a504b0a` · category `classify` · out tokens 5→22

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.25 — sequence similarity 0.25 (threshold 0.8)

<details><summary>Prompt</summary>

```text
[system] You are a precise assistant. Answer directly and concisely. No preamble.

[user] Route this support ticket (billing/technical/account/shipping): 'The app crashes when I open settings.'
```

</details>
<details><summary>Baseline (gpt-4o-mini-2024-07-18)</summary>

```text
Route to technical support.
```

</details>
<details><summary>Target (claude-haiku-4-5-20251001)</summary>

```text
**Technical**

This is a software functionality issue requiring troubleshooting and bug investigation.
```

</details>

## Pricing

_Cost is derived at report time from recorded tokens and the snapshots below; cassettes store tokens only. `*` marks estimates where some token categories had no rate in the profile._

- **anthropic-list+openai-list** (USD, as-of latest):
  - snapshot `anthropic-list/2026-06-12.json` (effective 2026-06-12, sha256 `8197d3770986…`)
  - snapshot `openai-list/2026-06-12.json` (effective 2026-06-12, sha256 `f850297a7d4f…`)
