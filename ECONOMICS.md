# ReviewRay — Economics & Market Analysis

## Market Size

### The Problem in Numbers

| Metric | Value | Source |
|--------|-------|--------|
| Online reviews that are fake | **30%** | FTC, 2025 |
| Consumer spending influenced by fake reviews | **$787B/year** (2025) | World Economic Forum |
| Projected cost by 2030 | **$1.07T/year** | Same study |
| Consumers who encounter fake reviews yearly | **82%** | Shapo.io |
| Consumers who won't buy if they suspect fakes | **>50%** | Capital One Shopping |
| Average money wasted per consumer/year on fake-review purchases | **$125** | ReviewDriver |
| AI-generated review growth rate | **80% MoM** since June 2023 | Shapo.io |
| Sales boost from fake reviews (first 2 weeks) | **+12.5%** | Marketing Science |
| Demand increase per additional star | **+38%** | Harvard Business School |

### TAM / SAM / SOM

```
TAM (Total Addressable Market)
├── Review integrity tools (consumer + enterprise):  ~$3.2B
├── Brand protection / counterfeit detection:        ~$1.8B
└── Total:                                           ~$5.0B

SAM (Serviceable Available Market)
├── Consumer review checker tools:                   ~$800M
├── E-commerce brand review monitoring:              ~$400M
└── Total:                                           ~$1.2B

SOM (Serviceable Obtainable Market) — Year 1-2
├── Free users (browser extension + web):            500K users
├── Paid conversions (3%):                           15K users
├── Average revenue per paid user:                   $9/mo = $108/yr
└── Year 2 ARR target:                               ~$1.6M
```

## Revenue Model

### Pricing Tiers

| Tier | Price | Includes | Target |
|------|-------|----------|--------|
| **Free** | $0 | 10 checks/day, Amazon only, web UI | Casual shoppers |
| **Consumer Pro** | $5/mo | Unlimited checks, all platforms, browser extension | Active online shoppers |
| **Power User** | $9/mo | + History, alerts, bulk check, export | Brand managers, researchers |
| **API** | $0.05/request | REST API, webhook support | Developers, integrations |
| **Enterprise** | $299/mo | Custom volume, SLA, dedicated support | E-commerce platforms, agencies |

### Revenue Projections (Conservative)

| | Month 6 | Month 12 | Month 24 |
|---|---------|----------|----------|
| Free users | 50K | 200K | 500K |
| Paid users | 500 | 3,000 | 15,000 |
| Conversion rate | 1% | 1.5% | 3% |
| MRR | $3,500 | $21,000 | $105,000 |
| ARR | $42K | $252K | $1.26M |
| API revenue/mo | $200 | $2,000 | $15,000 |
| **Total ARR** | **$44K** | **$276K** | **$1.44M** |

### Revenue Projections (Optimistic)

| | Month 6 | Month 12 | Month 24 |
|---|---------|----------|----------|
| Free users | 100K | 500K | 2M |
| Paid users | 2,000 | 15,000 | 80,000 |
| Conversion rate | 2% | 3% | 4% |
| MRR | $14,000 | $105,000 | $560,000 |
| ARR | $168K | $1.26M | $6.72M |

## Cost Structure

### Infrastructure (per month)

| Component | Free tier (MVP) | Growth ($20K MRR) | Scale ($100K MRR) |
|-----------|----------------|--------------------|--------------------|
| VPS / Cloud | $20 (Hetzner) | $150 (2x dedicated) | $800 (k8s cluster) |
| Database (SQLite → Postgres) | $0 | $30 (managed) | $100 |
| CDN / Proxy | $0 (Cloudflare free) | $20 | $200 |
| Monitoring | $0 (self-hosted) | $30 | $100 |
| **Total infra** | **$20/mo** | **$230/mo** | **$1,200/mo** |

### Cost Per Analysis

| Component | Cost | Notes |
|-----------|------|-------|
| HTTP request to scrape reviews | ~$0.001 | BeautifulSoup, no API costs |
| Text similarity computation | ~$0.0005 | CPU-only, shingle hashing |
| Statistical analysis | ~$0.0001 | Pure math, negligible |
| Storage (result caching) | ~$0.0001 | SQLite/Postgres |
| **Total per analysis** | **~$0.002** | No LLM API needed |

**Key advantage vs competitors:** Null Fake uses GPT-4 at ~$0.03-0.10 per analysis. ReviewRay runs locally at $0.002 — **15-50x cheaper per request.**

### Team (projected)

| Phase | Headcount | Monthly cost |
|-------|-----------|-------------|
| MVP (now) | 1 solo dev (agent) | $0 |
| Growth (MRR $10K+) | + 1 frontend dev | $3,000 |
| Scale (MRR $50K+) | + 1 ML engineer, 1 marketing | $12,000 |

## Unit Economics

### Per-User Economics

| Metric | Free user | Pro $9/mo |
|--------|-----------|-----------|
| Avg analyses/month | 15 | 80 |
| Cost to serve | $0.03/mo | $0.16/mo |
| Revenue | $0 | $9/mo |
| Gross margin | N/A | **98.2%** |
| Monthly contribution | -$0.03 | +$8.84 |

### Key SaaS Metrics (Month 24 target)

| Metric | Value | Benchmark |
|--------|-------|-----------|
| Gross margin | **98%** | Good SaaS: 70-85% |
| CAC (organic/viral) | **$2-5** | Freemium avg: $10-50 |
| LTV (Pro, 14mo avg life) | **$126** | — |
| LTV/CAC ratio | **25-63x** | Good: >3x |
| Payback period | **<1 month** | Good: <12 months |
| Churn (monthly) | ~7% est. | Consumer SaaS avg: 5-10% |
| Net Revenue Retention | ~95% est. | Good: >100% |

## Growth Strategy

### Phase 1: Launch (Months 1-3)
- Ship browser extension (Chrome → Firefox)
- SEO: target "fakespot alternative", "fake review checker", "is this product legit"
- Reddit organic: r/BuyItForLife, r/AmazonBestOf, r/Frugal, r/DealsReddit
- Product Hunt launch
- **Goal: 50K free users**

### Phase 2: Growth (Months 4-12)
- Add Google Maps, Trustpilot, App Store
- API launch for developers
- Partnership with deal/coupon sites (Honey, RetailMeNot)
- Affiliate model: recommend verified-good products
- **Goal: 200K free, 3K paid, $21K MRR**

### Phase 3: Scale (Months 12-24)
- Enterprise tier for e-commerce platforms
- White-label API for price comparison sites
- ML model improvements (BERT-based review classifier)
- Mobile app (iOS/Android)
- **Goal: 500K+ free, 15K paid, $105K MRR**

## Competitive Moat

1. **Zero API cost** — no dependency on OpenAI/Anthropic. Pure algorithmic analysis scales infinitely.
2. **Russian market** — only tool supporting Wildberries (50M+ monthly users). No competition.
3. **Open source** — builds trust, enables community contributions, reduces marketing costs.
4. **Multi-platform by design** — architecture supports adding any review source as a plugin.
5. **Data network effect** — more analyses = better statistical baselines per product category.

## Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Platforms block scraping | High | Medium | Rotate user agents, use official APIs where available, consider browser extension (client-side) |
| AI reviews become undetectable | Medium | Low (near-term) | Add ML classifier, behavioral signals beyond text |
| Competitor with funding enters | Medium | Medium | Speed + open source + niche (RU market) |
| Low conversion rate (<1%) | High | Medium | Optimize paywall triggers, add premium-only platforms |
| Legal (TOS violations) | Medium | Low | Comply with CFAA, use public data only, no login required |

## Exit Scenarios

| Scenario | Timeline | Valuation Multiple | Est. Value |
|----------|----------|-------------------|------------|
| Acqui-hire by e-commerce platform | 1-2 years | — | $500K-2M |
| Acquisition by security/trust company | 2-3 years | 8-12x ARR | $2-15M |
| Independent growth to profitability | 3+ years | 10-15x ARR | $10-20M |
| Strategic acquisition (Amazon, Google) | 3-5 years | 15-20x ARR | $15-30M |

---

*Analysis by RedditScoutAgent-42 · March 2026*
*Sources: FTC (2025), World Economic Forum, Capital One Shopping Research, Harvard Business School, Marketing Science, First Page Sage SaaS Benchmarks*
