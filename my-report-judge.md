# Migration Report — gpt-4o-mini-2024-07-18 → claude-haiku-4-5

`corpus` · target `claude-haiku-4-5` (anthropic) · generated 2026-07-01T19:22:14+00:00 · comparators exact, fuzzy, judge

**100 compared** (100 cached, 0 live) · 0 skipped · 0 errored

## Summary

| Comparator | Passed | Pass rate | Mean score |
|---|---:|---:|---:|
| exact | 22/100 | 22% | 0.22 |
| fuzzy | 48/100 | 48% | 0.65 |
| judge | 94/100 | 94% | 0.92 |

| Metric | Baseline | Target | Ratio |
|---|---:|---:|---:|
| Output tokens | 1,435 | 3,059 | 2.13× |
| Est. cost (anthropic-list+openai-list) | $0.001658 | $0.020655 | 12.46× |

## By category

_Cells are pass rate · mean score. Out tokens and Latency are target/baseline ratios._

| Category | Prompts | exact | fuzzy | judge | Out tokens | Latency | Cost (anthropic-list+openai-list) |
|---|---:|---:|---:|---:|---:|---:|---:|
| classify | 30 | 7% · 0.07 | 13% · 0.25 | 83% · 0.81 | 9.40× | – | 25.16× |
| extract | 30 | 57% · 0.57 | 93% · 0.95 | 100% · 0.98 | 1.42× | – | 9.69× |
| rewrite | 15 | 13% · 0.13 | 40% · 0.72 | 93% · 0.92 | 1.65× | – | 10.45× |
| summarize | 15 | 0% · 0.00 | 7% · 0.62 | 100% · 0.96 | 1.18× | – | 8.60× |
| translate | 10 | 10% · 0.10 | 90% · 0.90 | 100% · 0.97 | 1.68× | – | 10.89× |

## Results

| # | Prompt | Category | Baseline model | exact | fuzzy | judge | Out tok | Latency | Cost (anthropic-list+openai-list) | Cached |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Extract as JSON {error_code, service} from this log line: '2026-06-11T09:14:02Z… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.98 | ✅ 0.90 | 23→32 | – | $0.000024→$0.000227 | ✅ |
| 2 | Extract as JSON {amount, currency}: 'Your total comes to $1,249.99 including ta… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 23→30 | – | $0.000021→$0.000199 | ✅ |
| 3 | Extract as JSON {checkin, checkout} as ISO dates: 'We'd like the room from Marc… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.84 | ✅ 0.95 | 45→38 | – | $0.000036→$0.00025 | ✅ |
| 4 | Fix grammar and spelling, return only the corrected text: 'Me and him was going… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.96 | ❌ 0.60 | 12→15 | – | $0.000015→$0.000129 | ✅ |
| 5 | Sentiment (positive/negative/neutral): 'Shipping was fast but the product broke… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.13 | ✅ 0.95 | 2→31 | – | $0.000009→$0.000203 | ✅ |
| 6 | Sentiment (positive/negative/neutral): 'Absolutely love it, exceeded every expe… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.52 | ✅ 1.00 | 1→10 | – | $0.000008→$0.000096 | ✅ |
| 7 | Is this about a delivery problem? (yes/no): 'The tracking number you sent does … | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.02 | ❌ 0.00 | 2→43 | – | $0.000009→$0.000263 | ✅ |
| 8 | Summarize this policy in one sentence: 'Employees may work remotely up to three… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.78 | ✅ 0.98 | 32→35 | – | $0.00003→$0.000247 | ✅ |
| 9 | Topic (billing/bug/feature_request/how_to): 'How do I add a teammate to my work… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.12 | ✅ 0.90 | 48→198 | – | $0.000036→$0.001042 | ✅ |
| 10 | Rewrite this error message to be user-friendly: 'ERR_CONN_5021: pool exhausted … | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.44 | ✅ 0.90 | 19→28 | – | $0.000019→$0.000194 | ✅ |
| 11 | Summarize the complaint in one sentence: 'I ordered a blue medium jacket but re… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.64 | ✅ 0.98 | 29→35 | – | $0.000027→$0.000238 | ✅ |
| 12 | Extract the contract end date as an ISO date: 'The agreement runs through 31 De… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 6→10 | – | $0.000012→$0.000104 | ✅ |
| 13 | Remove the filler words: 'So basically we just kind of need to actually finaliz… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.97 | ✅ 0.99 | 8→13 | – | $0.000012→$0.000114 | ✅ |
| 14 | Normalize this address into one line with proper capitalization: 'lagerstrasse … | rewrite | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 0.95 | 12→18 | – | $0.000015→$0.000142 | ✅ |
| 15 | Turn this into a polite decline: 'No, we won't build that feature.' | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.52 | ✅ 0.95 | 20→33 | – | $0.000019→$0.000209 | ✅ |
| 16 | Extract as JSON {temperature_c, sensor}: 'Sensor 7 in the cold room reads -18.5… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 23→30 | – | $0.000022→$0.000206 | ✅ |
| 17 | Replace all personal data with [REDACTED]: 'Contact Anna Larsen at +45 22 11 33… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.98 | ✅ 1.00 | 25→24 | – | $0.000024→$0.000183 | ✅ |
| 18 | Rewrite as a single bullet point: 'The meeting covered the hiring plan, the off… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.91 | ✅ 0.98 | 15→19 | – | $0.000017→$0.000147 | ✅ |
| 19 | Extract as JSON {sku, quantity}: 'Please ship 12 units of SKU-44821 to the Hamb… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.93 | ✅ 1.00 | 16→31 | – | $0.000017→$0.000209 | ✅ |
| 20 | Extract the IBAN: 'Please wire the deposit to IBAN DE89 3704 0044 0532 0130 00 … | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.90 | ✅ 0.98 | 16→11 | – | $0.000019→$0.000116 | ✅ |
| 21 | Route this support ticket (billing/technical/account/shipping): 'I can't reset … | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.10 | ❌ 0.40 | 1→6 | – | $0.000008→$0.000077 | ✅ |
| 22 | Spam or not spam: 'Hi Sam, can we move our 2pm meeting to 3pm tomorrow?' | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.16 | ✅ 0.95 | 3→23 | – | $0.000009→$0.000166 | ✅ |
| 23 | Intent (question/complaint/praise/refund_request): 'The blender stopped working… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.19 | ✅ 0.90 | 3→37 | – | $0.00001→$0.00024 | ✅ |
| 24 | Language of this text (ISO 639-1 code only): '¿Dónde está la estación de tren?' | classify | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 1→4 | – | $0.000008→$0.000075 | ✅ |
| 25 | Extract as JSON {flight, gate}: 'Flight UA287 is now boarding at gate B14.' | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 22→29 | – | $0.00002→$0.000192 | ✅ |
| 26 | Topic (billing/bug/feature_request/how_to): 'It would be great if exports suppo… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.24 | ✅ 0.95 | 3→29 | – | $0.000009→$0.000195 | ✅ |
| 27 | Spam or not spam: 'Congratulations! You won a $1000 gift card, click here to cl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.05 | ✅ 0.90 | 2→54 | – | $0.000009→$0.000322 | ✅ |
| 28 | Summarize this review in one sentence: 'I have used this laptop for three month… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.71 | ✅ 0.98 | 24→30 | – | $0.000025→$0.000224 | ✅ |
| 29 | One-sentence executive summary: 'Q2 churn rose from 4% to 6%, driven by small-b… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.61 | ✅ 0.85 | 34→31 | – | $0.000031→$0.000224 | ✅ |
| 30 | Extract the invoice number: 'Re: outstanding payment for invoice INV-2026-0457.' | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 7→11 | – | $0.000011→$0.000102 | ✅ |
| 31 | Extract all URLs as a JSON array: 'Docs moved to https://docs.example.com/v2; o… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.98 | ✅ 1.00 | 21→36 | – | $0.000021→$0.000242 | ✅ |
| 32 | Priority (low/medium/high/urgent): 'Checkout intermittently fails for about 10%… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.08 | ✅ 0.90 | 3→86 | – | $0.000009→$0.000481 | ✅ |
| 33 | Extract as JSON {from, to} airport codes: 'Searching flights CPH to JFK for two… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 22→29 | – | $0.000021→$0.000195 | ✅ |
| 34 | Extract as JSON {city, country}: 'Our HQ is in Lyon, France, with a satellite o… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.98 | ✅ 1.00 | 33→55 | – | $0.000028→$0.000326 | ✅ |
| 35 | Summarize the risk in one sentence: 'While the merger promises cost savings thr… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.46 | ✅ 0.98 | 20→25 | – | $0.000021→$0.000185 | ✅ |
| 36 | Does this text contain personal data? (yes/no): 'My SSN is 523-12-9876, please … | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.86 | ✅ 1.00 | 2→4 | – | $0.00001→$0.000076 | ✅ |
| 37 | Translate to Dutch: 'Your invoice is attached as a PDF.' | translate | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 10→18 | – | $0.000012→$0.00013 | ✅ |
| 38 | Extract all dates as a JSON array of ISO dates: 'The invoice was issued 2026-03… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 20→24 | – | $0.000021→$0.000181 | ✅ |
| 39 | Neutralize the tone for a status update: 'The vendor STILL has not fixed their … | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.66 | ✅ 0.98 | 16→22 | – | $0.000018→$0.000165 | ✅ |
| 40 | Condense this email to one sentence: 'Following up on our call - attached is th… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.76 | ✅ 0.95 | 22→37 | – | $0.000024→$0.000256 | ✅ |
| 41 | Churn risk (low/medium/high): 'We're evaluating alternatives because prices wen… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.00 | ❌ 0.20 | 2→106 | – | $0.000008→$0.000579 | ✅ |
| 42 | Summarize the incident impact in one sentence: 'The pricing bug showed VAT-excl… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.74 | ✅ 0.99 | 28→36 | – | $0.000027→$0.000249 | ✅ |
| 43 | Translate to Swedish: 'Your payment could not be processed. Please check your c… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.97 | ✅ 0.99 | 19→27 | – | $0.000018→$0.00018 | ✅ |
| 44 | Extract the tracking number: 'Your parcel 1Z999AA10123456784 left our facility … | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 8→12 | – | $0.000012→$0.000111 | ✅ |
| 45 | Extract the last four card digits: 'The charge went to the Visa ending in 4242.' | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 2→6 | – | $0.000008→$0.000077 | ✅ |
| 46 | Intent (question/complaint/praise/refund_request): 'Your support team solved my… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.10 | ✅ 0.95 | 1→25 | – | $0.000008→$0.000174 | ✅ |
| 47 | Extract as JSON {name, company}: 'Hi, this is Maria Gonzalez calling from Acme … | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.98 | ✅ 1.00 | 19→36 | – | $0.00002→$0.000239 | ✅ |
| 48 | Summarize this support thread in one sentence: 'Customer reported login failure… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.38 | ✅ 0.95 | 20→34 | – | $0.000024→$0.000248 | ✅ |
| 49 | Priority (low/medium/high/urgent): 'A tooltip on the settings page has a small … | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.13 | ✅ 0.95 | 3→44 | – | $0.000009→$0.000269 | ✅ |
| 50 | Make this subject line professional: 'wanna chat about the budget thing' | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.43 | ✅ 0.90 | 7→18 | – | $0.000011→$0.000131 | ✅ |
| 51 | Extract as JSON {product, issue}: 'The X200 vacuum's battery drains within ten … | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.97 | ✅ 1.00 | 19→35 | – | $0.000019→$0.000223 | ✅ |
| 52 | Rewrite for a non-technical audience: 'The outage was caused by an expired TLS … | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.50 | ✅ 0.85 | 15→24 | – | $0.000017→$0.000174 | ✅ |
| 53 | Translate to Polish: 'Two-factor authentication is now enabled on your account.' | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.91 | ✅ 0.97 | 24→29 | – | $0.000021→$0.000188 | ✅ |
| 54 | Extract the order number: 'Hello, I'm writing about order #84412-B which arrive… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.50 | ✅ 0.98 | 3→11 | – | $0.000009→$0.000103 | ✅ |
| 55 | Spam or not spam: 'URGENT: verify your account within 24 hours or it will be su… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.00 | ✅ 0.95 | 2→64 | – | $0.000009→$0.00037 | ✅ |
| 56 | Make this concise (max 10 words): 'Due to the fact that it was raining, we made… | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.70 | ✅ 0.97 | 10→14 | – | $0.000014→$0.000128 | ✅ |
| 57 | Extract as JSON {street, zip, city}: 'Send returns to Lagerstrasse 12, 20095 Ha… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 34→42 | – | $0.000029→$0.000269 | ✅ |
| 58 | Sentiment (positive/negative/neutral): 'It's fine. Does the job, nothing specia… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.06 | ✅ 0.90 | 2→47 | – | $0.000008→$0.000282 | ✅ |
| 59 | Headline (max 8 words) for this update: 'The mobile app now supports offline mo… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.64 | ✅ 0.90 | 9→19 | – | $0.000015→$0.000159 | ✅ |
| 60 | Topic (billing/bug/feature_request/how_to): 'The dashboard shows a 500 error wh… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.42 | ✅ 0.95 | 20→42 | – | $0.00002→$0.000264 | ✅ |
| 61 | Rewrite in active voice: 'The proposal was reviewed by the committee.' | rewrite | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 6→9 | – | $0.00001→$0.000087 | ✅ |
| 62 | Translate to Spanish: 'Click the link below to reset your password.' | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.99 | ✅ 1.00 | 15→24 | – | $0.000015→$0.000161 | ✅ |
| 63 | Does this text contain personal data? (yes/no): 'Bad weather in the region dela… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.80 | ✅ 1.00 | 2→4 | – | $0.000009→$0.000069 | ✅ |
| 64 | Translate to Italian: 'The item is currently out of stock.' | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.97 | ✅ 1.00 | 10→14 | – | $0.000012→$0.00011 | ✅ |
| 65 | Extract all monetary amounts as a JSON array: 'Setup costs $500, then $99 per m… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.70 | ✅ 0.85 | 13→26 | – | $0.000016→$0.000186 | ✅ |
| 66 | Soften this for a performance review: 'Your code is sloppy and full of bugs.' | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.44 | ✅ 0.85 | 14→33 | – | $0.000015→$0.000212 | ✅ |
| 67 | Translate to German: 'Your order has been shipped and will arrive in 3-5 busine… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.52 | ✅ 0.90 | 19→56 | – | $0.000019→$0.000329 | ✅ |
| 68 | Extract the version number: 'After updating to v2.14.3 the export button disapp… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.92 | ✅ 0.95 | 5→9 | – | $0.00001→$0.000092 | ✅ |
| 69 | One-line summary of this changelog: 'Fixed a memory leak in the upload handler,… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.47 | ✅ 0.98 | 19→22 | – | $0.000021→$0.00017 | ✅ |
| 70 | Extract the action items as a JSON array: 'John will email the report, Lisa boo… | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.90 | ✅ 0.95 | 66→91 | – | $0.000048→$0.000511 | ✅ |
| 71 | Translate to French: 'Your subscription will renew on July 1st.' | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.93 | ✅ 0.97 | 11→21 | – | $0.000013→$0.000148 | ✅ |
| 72 | TL;DR of these meeting notes in one sentence: 'We agreed to ship the beta on Ju… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.63 | ✅ 0.98 | 34→42 | – | $0.000032→$0.000287 | ✅ |
| 73 | Summarize in one sentence for a status page: 'Between 09:12 and 10:47 UTC some … | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.46 | ✅ 0.95 | 39→35 | – | $0.000035→$0.000255 | ✅ |
| 74 | Route this support ticket (billing/technical/account/shipping): 'How do I downl… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.17 | ❌ 0.10 | 5→24 | – | $0.000011→$0.000172 | ✅ |
| 75 | Rewrite politely for a customer email: 'Send me the report now.' | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.70 | ✅ 0.90 | 15→35 | – | $0.000015→$0.000218 | ✅ |
| 76 | Extract the username: 'User @data_wrangler_88 reported the sync issue first.' | extract | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.97 | ✅ 0.95 | 6→11 | – | $0.000011→$0.000102 | ✅ |
| 77 | Extract the phone number: 'Call our support line at (415) 555-0132 between 9 an… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 8→11 | – | $0.000013→$0.000109 | ✅ |
| 78 | Sentiment (positive/negative/neutral): 'Third time my delivery is late. I want … | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.13 | ✅ 0.95 | 2→31 | – | $0.000009→$0.000204 | ✅ |
| 79 | Translate to Norwegian: 'Your return has been received and your refund is on it… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.91 | ✅ 0.98 | 16→22 | – | $0.000016→$0.000156 | ✅ |
| 80 | Extract as JSON {day, time, timezone}: 'Let's sync Thursday at 14:30 CET on the… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 30→38 | – | $0.000026→$0.000244 | ✅ |
| 81 | Make this more formal: 'Hey, can you take a look at this when you get a sec?' | rewrite | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.60 | ✅ 0.95 | 11→34 | – | $0.000014→$0.000218 | ✅ |
| 82 | Translate to Danish: 'Thank you for contacting support. We will reply within 24… | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.88 | ✅ 0.97 | 16→24 | – | $0.000017→$0.000168 | ✅ |
| 83 | Churn risk (low/medium/high): 'Renewed for another year, the new features are g… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.03 | ✅ 0.95 | 1→39 | – | $0.000008→$0.000245 | ✅ |
| 84 | Route this support ticket (billing/technical/account/shipping): 'I was charged … | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.56 | ✅ 1.00 | 1→9 | – | $0.000008→$0.000092 | ✅ |
| 85 | Extract the license plate: 'The delivery van, plate HH-AB 1234, was parked at d… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 6→10 | – | $0.000012→$0.000103 | ✅ |
| 86 | Extract as JSON {employee_id, department}: 'Badge E-20331 belongs to Priya Nair… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 25→33 | – | $0.000023→$0.00022 | ✅ |
| 87 | Priority (low/medium/high/urgent): 'Login is broken for all users in production… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.06 | ✅ 0.90 | 4→123 | – | $0.000009→$0.000661 | ✅ |
| 88 | Summarize for a shift handover in one sentence: 'Night shift saw two failed bat… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.93 | ✅ 0.98 | 30→31 | – | $0.000029→$0.000228 | ✅ |
| 89 | Language of this text (ISO 639-1 code only): 'Hvor er nærmeste togstation?' | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.00 | ❌ 0.00 | 1→4 | – | $0.000008→$0.000071 | ✅ |
| 90 | Intent (question/complaint/praise/refund_request): 'Why is my order still not h… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.19 | ✅ 0.90 | 2→23 | – | $0.000009→$0.000167 | ✅ |
| 91 | Extract the names of all people mentioned as a JSON array: 'Tom and Aisha met w… | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 16→23 | – | $0.000018→$0.000171 | ✅ |
| 92 | Moderation (allowed/flagged): 'You are an idiot and your product is garbage.' | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.01 | ✅ 0.90 | 3→48 | – | $0.000009→$0.000287 | ✅ |
| 93 | Language of this text (ISO 639-1 code only): 'Wo ist der nächste Bahnhof?' | classify | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 1→4 | – | $0.000008→$0.000075 | ✅ |
| 94 | Route this support ticket (billing/technical/account/shipping): 'My package sho… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.12 | ✅ 0.95 | 1→29 | – | $0.000008→$0.000193 | ✅ |
| 95 | Translate to Portuguese: 'Free shipping on orders over 50 euros.' | translate | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ✅ 0.88 | ✅ 0.97 | 12→20 | – | $0.000014→$0.000142 | ✅ |
| 96 | Extract the email address: 'Reach me at jane.doe+work@example.co.uk anytime.' | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 9→14 | – | $0.000012→$0.00012 | ✅ |
| 97 | Summarize this bug report in one sentence: 'Steps: open the editor, paste a tab… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.47 | ✅ 0.98 | 39→39 | – | $0.000036→$0.000277 | ✅ |
| 98 | Summarize the recurring feedback theme in one sentence: 'Across 80 survey respo… | summarize | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.58 | ✅ 0.98 | 22→21 | – | $0.000023→$0.000173 | ✅ |
| 99 | Extract the discount percentage: 'Use code SPRING for 15% off your first order.' | extract | gpt-4o-mini-2024-07-18 | ✅ 1.00 | ✅ 1.00 | ✅ 1.00 | 2→6 | – | $0.000008→$0.000075 | ✅ |
| 100 | Route this support ticket (billing/technical/account/shipping): 'The app crashe… | classify | gpt-4o-mini-2024-07-18 | ❌ 0.00 | ❌ 0.25 | ✅ 0.95 | 5→22 | – | $0.00001→$0.000158 | ✅ |

## Details

_Failing rows first, then lowest mean score._

### 89. Language of this text (ISO 639-1 code only): 'Hvor er nærmeste togstation?'

`openai_gpt-4o-mini_d9d019d6590c4ea8` → `migration__openai_gpt-4o-mini_d9d019d6590c4ea8__to__claude-haiku-4-5` · semantic key `629a8cca6370942fa25d6a5b5b19c789` · category `classify` · out tokens 1→4

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.00 — sequence similarity 0.00 (threshold 0.8)
- **judge** ❌ 0.00 — The text is Danish (da), so the candidate's 'no' (Norwegian) is incorrect.

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

### 7. Is this about a delivery problem? (yes/no): 'The tracking number you sent does …

`openai_gpt-4o-mini_18e0f38c9da3089d` → `migration__openai_gpt-4o-mini_18e0f38c9da3089d__to__claude-haiku-4-5` · semantic key `a49ec22ca5d985abc6a7bc862079e686` · category `classify` · out tokens 2→43

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.02 — sequence similarity 0.02 (threshold 0.8)
- **judge** ❌ 0.00 — The baseline answers 'Yes' while the candidate answers 'No', giving opposite conclusions to the yes/no question.

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

### 41. Churn risk (low/medium/high): 'We're evaluating alternatives because prices wen…

`openai_gpt-4o-mini_69a66c3ebce30c3a` → `migration__openai_gpt-4o-mini_69a66c3ebce30c3a__to__claude-haiku-4-5` · semantic key `c8437a70cc226f4269e81d6e5376ae31` · category `classify` · out tokens 2→106

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.00 — sequence similarity 0.00 (threshold 0.8)
- **judge** ❌ 0.20 — The baseline rates the churn risk as medium while the candidate rates it high, a direct disagreement on the core classification asked for.

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

### 74. Route this support ticket (billing/technical/account/shipping): 'How do I downl…

`openai_gpt-4o-mini_bf4cf18052faa0ad` → `migration__openai_gpt-4o-mini_bf4cf18052faa0ad__to__claude-haiku-4-5` · semantic key `4ccf03628906ff9b4509f832b641196e` · category `classify` · out tokens 5→24

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.17 — sequence similarity 0.17 (threshold 0.8)
- **judge** ❌ 0.10 — Baseline routes to billing while candidate routes to account, a different category for the invoice-related ticket.

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

### 21. Route this support ticket (billing/technical/account/shipping): 'I can't reset …

`openai_gpt-4o-mini_37d5392016c26bcf` → `migration__openai_gpt-4o-mini_37d5392016c26bcf__to__claude-haiku-4-5` · semantic key `014d3b6bef5d2295c99480cd61a3d3fa` · category `classify` · out tokens 1→6

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.10 — sequence similarity 0.10 (threshold 0.8)
- **judge** ❌ 0.40 — The two responses assign different categories (technical vs account) to the same ticket, so they are not semantically equivalent.

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

### 92. Moderation (allowed/flagged): 'You are an idiot and your product is garbage.'

`openai_gpt-4o-mini_e0084440d3367cc4` → `migration__openai_gpt-4o-mini_e0084440d3367cc4__to__claude-haiku-4-5` · semantic key `ef72cd51a90ab8b41807dd733ad60e26` · category `classify` · out tokens 3→48

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.01 — sequence similarity 0.01 (threshold 0.8)
- **judge** ✅ 0.90 — Both classify the content as flagged; candidate adds explanatory detail but reaches the same moderation decision.

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

### 27. Spam or not spam: 'Congratulations! You won a $1000 gift card, click here to cl…

`openai_gpt-4o-mini_43b5d4942e1dbb79` → `migration__openai_gpt-4o-mini_43b5d4942e1dbb79__to__claude-haiku-4-5` · semantic key `d06b7828215d1d402bb38e045ddc029b` · category `classify` · out tokens 2→54

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.05 — sequence similarity 0.05 (threshold 0.8)
- **judge** ✅ 0.90 — Both correctly classify as spam; candidate adds explanatory detail but reaches the same conclusion.

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

### 55. Spam or not spam: 'URGENT: verify your account within 24 hours or it will be su…

`openai_gpt-4o-mini_91e3187c78aa9a93` → `migration__openai_gpt-4o-mini_91e3187c78aa9a93__to__claude-haiku-4-5` · semantic key `027bfa9a19cdee5b43841a6771753a21` · category `classify` · out tokens 2→64

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.00 — sequence similarity 0.00 (threshold 0.8)
- **judge** ✅ 0.95 — Both classify the message as spam; the candidate adds explanatory detail but reaches the same conclusion.

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

### 87. Priority (low/medium/high/urgent): 'Login is broken for all users in production…

`openai_gpt-4o-mini_d80e914e1872be3d` → `migration__openai_gpt-4o-mini_d80e914e1872be3d__to__claude-haiku-4-5` · semantic key `c84aa056273b4bbde705343b1d599ddd` · category `classify` · out tokens 4→123

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.06 — sequence similarity 0.06 (threshold 0.8)
- **judge** ✅ 0.90 — Both classify the priority as Urgent; candidate adds extra detail but the core answer matches despite the prompt requesting conciseness.

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

### 58. Sentiment (positive/negative/neutral): 'It's fine. Does the job, nothing specia…

`openai_gpt-4o-mini_971ceef22d00b451` → `migration__openai_gpt-4o-mini_971ceef22d00b451__to__claude-haiku-4-5` · semantic key `5bf36323c5f6371744833313a4747986` · category `classify` · out tokens 2→47

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.06 — sequence similarity 0.06 (threshold 0.8)
- **judge** ✅ 0.90 — Both classify the sentiment as neutral; the candidate adds explanatory detail despite the concise instruction, but the core answer matches.

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

### 32. Priority (low/medium/high/urgent): 'Checkout intermittently fails for about 10%…

`openai_gpt-4o-mini_508d047cade5d1a6` → `migration__openai_gpt-4o-mini_508d047cade5d1a6__to__claude-haiku-4-5` · semantic key `b52db60497916ee283c01911dd51152a` · category `classify` · out tokens 3→86

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.08 — sequence similarity 0.08 (threshold 0.8)
- **judge** ✅ 0.90 — Both classify the priority as High; the candidate adds justification and caveats but reaches the same core answer despite violating the concise/no-preamble instruction.

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

### 83. Churn risk (low/medium/high): 'Renewed for another year, the new features are g…

`openai_gpt-4o-mini_d08713e52b495d5f` → `migration__openai_gpt-4o-mini_d08713e52b495d5f__to__claude-haiku-4-5` · semantic key `c073f1bc0de9ceee4df90d02e169d104` · category `classify` · out tokens 1→39

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.03 — sequence similarity 0.03 (threshold 0.8)
- **judge** ✅ 0.95 — Both classify churn risk as Low; candidate adds explanation but the core answer matches despite the no-preamble instruction.

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

### 9. Topic (billing/bug/feature_request/how_to): 'How do I add a teammate to my work…

`openai_gpt-4o-mini_1b7f67df4a19f8dc` → `migration__openai_gpt-4o-mini_1b7f67df4a19f8dc__to__claude-haiku-4-5` · semantic key `cdae929542ed548a8e57aca83344fb80` · category `classify` · out tokens 48→198

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.12 — sequence similarity 0.12 (threshold 0.8)
- **judge** ✅ 0.90 — Both give the same core steps (settings, invite by email, send invitation) with the candidate adding extra role/permission details but semantically equivalent.

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

### 46. Intent (question/complaint/praise/refund_request): 'Your support team solved my…

`openai_gpt-4o-mini_719d4d1be2fdf365` → `migration__openai_gpt-4o-mini_719d4d1be2fdf365__to__claude-haiku-4-5` · semantic key `95064c205282f4218605fc238b7a16c7` · category `classify` · out tokens 1→25

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.10 — sequence similarity 0.10 (threshold 0.8)
- **judge** ✅ 0.95 — Both correctly classify the intent as praise; the candidate adds a brief explanation but the core answer matches.

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

### 94. Route this support ticket (billing/technical/account/shipping): 'My package sho…

`openai_gpt-4o-mini_ee8e8bb716aaf7ba` → `migration__openai_gpt-4o-mini_ee8e8bb716aaf7ba__to__claude-haiku-4-5` · semantic key `fb1e148017a6803bf11d3d0a11582df0` · category `classify` · out tokens 1→29

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.12 — sequence similarity 0.12 (threshold 0.8)
- **judge** ✅ 0.95 — Both route the ticket to Shipping; candidate adds explanatory preamble against instructions but the substantive answer is identical.

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

### 78. Sentiment (positive/negative/neutral): 'Third time my delivery is late. I want …

`openai_gpt-4o-mini_c6f34a2dbb588911` → `migration__openai_gpt-4o-mini_c6f34a2dbb588911__to__claude-haiku-4-5` · semantic key `b34a1e8841bcfaa4226ea10d738a5154` · category `classify` · out tokens 2→31

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.13 — sequence similarity 0.13 (threshold 0.8)
- **judge** ✅ 0.95 — Both correctly classify sentiment as negative; candidate adds justification but the core answer is identical.

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

### 5. Sentiment (positive/negative/neutral): 'Shipping was fast but the product broke…

`openai_gpt-4o-mini_0d22317379c5e062` → `migration__openai_gpt-4o-mini_0d22317379c5e062__to__claude-haiku-4-5` · semantic key `03be769ed6dcff44db3d26045168f978` · category `classify` · out tokens 2→31

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.13 — sequence similarity 0.13 (threshold 0.8)
- **judge** ✅ 0.95 — Both classify the sentiment as negative; the candidate adds brief justification but conveys the same answer despite the instruction to be concise.

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

### 49. Priority (low/medium/high/urgent): 'A tooltip on the settings page has a small …

`openai_gpt-4o-mini_7dff935818428c9d` → `migration__openai_gpt-4o-mini_7dff935818428c9d__to__claude-haiku-4-5` · semantic key `7c6853ae24d2c12058dc8aca810a418d` · category `classify` · out tokens 3→44

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.13 — sequence similarity 0.13 (threshold 0.8)
- **judge** ✅ 0.95 — Both classify the priority as Low; the candidate adds justification but reaches the same substantive answer despite the 'no preamble' instruction.

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

### 90. Intent (question/complaint/praise/refund_request): 'Why is my order still not h…

`openai_gpt-4o-mini_dab2ba3fba1c2c28` → `migration__openai_gpt-4o-mini_dab2ba3fba1c2c28__to__claude-haiku-4-5` · semantic key `a9852fe03e6143801baea8c1d1cd5cd8` · category `classify` · out tokens 2→23

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.19 — sequence similarity 0.19 (threshold 0.8)
- **judge** ✅ 0.90 — Both classify the intent as complaint; candidate adds minor explanation but the core answer matches.

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

### 23. Intent (question/complaint/praise/refund_request): 'The blender stopped working…

`openai_gpt-4o-mini_3d25d5ef9bc6a08a` → `migration__openai_gpt-4o-mini_3d25d5ef9bc6a08a__to__claude-haiku-4-5` · semantic key `567604ac5581ce8758b2be9a66bf756d` · category `classify` · out tokens 3→37

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.19 — sequence similarity 0.19 (threshold 0.8)
- **judge** ✅ 0.90 — Both correctly classify the intent as a refund request; the candidate adds explanation but the core answer matches.

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

### 22. Spam or not spam: 'Hi Sam, can we move our 2pm meeting to 3pm tomorrow?'

`openai_gpt-4o-mini_39c0d06de1f8b940` → `migration__openai_gpt-4o-mini_39c0d06de1f8b940__to__claude-haiku-4-5` · semantic key `c8064709cfc5372f50f9983ffe382dc5` · category `classify` · out tokens 3→23

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.16 — sequence similarity 0.16 (threshold 0.8)
- **judge** ✅ 0.95 — Both classify as not spam; candidate adds brief justification but core answer is identical.

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

### 26. Topic (billing/bug/feature_request/how_to): 'It would be great if exports suppo…

`openai_gpt-4o-mini_43a46c2898a7ac58` → `migration__openai_gpt-4o-mini_43a46c2898a7ac58__to__claude-haiku-4-5` · semantic key `2ba2e95c8a199d9e9d4582cb0f381f4b` · category `classify` · out tokens 3→29

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.24 — sequence similarity 0.24 (threshold 0.8)
- **judge** ✅ 0.95 — Both correctly classify as feature_request; candidate adds minor explanation but the substantive answer is identical.

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

### 100. Route this support ticket (billing/technical/account/shipping): 'The app crashe…

`openai_gpt-4o-mini_f7fe0e021a97d678` → `migration__openai_gpt-4o-mini_f7fe0e021a97d678__to__claude-haiku-4-5` · semantic key `ed3788822c7af6968f88bcb94a504b0a` · category `classify` · out tokens 5→22

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.25 — sequence similarity 0.25 (threshold 0.8)
- **judge** ✅ 0.95 — Both route the ticket to technical support; candidate adds brief justification but the classification matches.

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

### 66. Soften this for a performance review: 'Your code is sloppy and full of bugs.'

`openai_gpt-4o-mini_a41653955a425c0c` → `migration__openai_gpt-4o-mini_a41653955a425c0c__to__claude-haiku-4-5` · semantic key `949a8d237ab83a85ad159a27bbcde40f` · category `rewrite` · out tokens 14→33

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.44 — sequence similarity 0.44 (threshold 0.8)
- **judge** ✅ 0.85 — Both soften the criticism into constructive feedback about code quality and bugs; candidate adds actionable suggestions but conveys the same core message.

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

### 48. Summarize this support thread in one sentence: 'Customer reported login failure…

`openai_gpt-4o-mini_783e9d41ed03ffc2` → `migration__openai_gpt-4o-mini_783e9d41ed03ffc2__to__claude-haiku-4-5` · semantic key `a3fd53885f3b2ddb7055dce2de11f611` · category `summarize` · out tokens 20→34

- **exact** ❌ 0.00 — normalized texts differ
- **fuzzy** ❌ 0.38 — sequence similarity 0.38 (threshold 0.8)
- **judge** ✅ 0.95 — Both accurately summarize the thread as mobile login failures caused by an expired certificate that engineering fixed and resolved.

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

_… 75 more rows omitted; see the Results table or pass `--max-detail-rows 0`._

## Pricing

_Cost is derived at report time from recorded tokens and the snapshots below; cassettes store tokens only. `*` marks estimates where some token categories had no rate in the profile._

- **anthropic-list+openai-list** (USD, as-of latest):
  - snapshot `anthropic-list/2026-06-12.json` (effective 2026-06-12, sha256 `8197d3770986…`)
  - snapshot `openai-list/2026-06-12.json` (effective 2026-06-12, sha256 `f850297a7d4f…`)
