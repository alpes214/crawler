# ML-Based Ranking Search Design

## Overview

This document describes the integration of a Machine Learning ranking model (LightGBM/XGBoost) into the existing Elasticsearch-based search architecture to improve search result relevance.

## Proposed Search Pipeline

```
User Query
    ↓
Query Processing (preprocessing, tokenization, normalization)
    ↓
Candidate Retrieval (Elasticsearch BM25/semantic search)
    ↓
Top-N Results (500-10,000 candidates)
    ↓
Feature Extraction (query features + document features)
    ↓
ML Ranking Model (LightGBM/XGBoost)
    ↓
Sort by ML Score
    ↓
Return Top-K Results (20-100)
```

---

## Architecture Integration Analysis

### Current Architecture (from SCALE_ARCHITECTURE_DIAGRAM.md)

**Current Search Flow** (Section 6):
```
User → API (POST /api/products/search {"query": "wireless headphones"})
     → Elasticsearch (SEARCH products index)
     → [Returns product IDs]
     → PostgreSQL (SELECT FROM products WHERE id IN (...))
     → Return results
```

**Current Elasticsearch Setup**:
- 20 nodes (3 master + 17 data nodes) per region
- Handles 3.4M search qps with 97% CDN+Redis caching
- Search capacity: 85K qps (with caching)
- Stores: product_id, product_name, description, brand, category, domain_name, created_at

**Current API Tier**:
- K8s deployment: 100-1000 replicas (auto-scaling)
- Resources: 2 CPU, 4Gi RAM per pod
- Target latency: <100ms p95 for simple queries, <3s for search queries

---

## Implementation Plan

### Phase 1: Infrastructure Setup

#### 1.1 Add ML Ranking Service

**New Component**: ML Ranking Service (Python microservice)

**Deployment**: Kubernetes with auto-scaling (10-50 replicas based on load)

**Location in Architecture**:
```
API Pods → ML Ranking Service → (Elasticsearch for candidate retrieval)
                               → (ClickHouse for precomputed features)
```

**Rationale**:
- Separate service: Isolates ML model complexity from API pods
- Independent scaling: ML ranking has different resource requirements than API
- Model deployment: Easier to update models without redeploying entire API
- Resource optimization: ML inference is CPU-intensive, separate resource allocation

---

#### 1.2 Model Storage & Versioning

**Production approach**: Store models in S3/MinIO with version control

**Benefits**:
- Hot-swap models without service redeployment
- A/B testing capability (run multiple model versions)
- Rollback capability (revert to previous version)
- Centralized model repository across regions

---

#### 1.3 Feature Store

**Challenge**: Extract features for 500-10K candidates with <100ms latency

**Solution: Multi-Tier Feature Storage**

**Tier 1: ClickHouse** (precomputed during parsing)
- **Compute features during parsing** (in parser worker)
- **Store in ClickHouse `product_features` table**
- **Features computed once, queried fast** (columnar storage)
- Examples:
  - Text features: title_length, description_length, title_char_count, word_count
  - Quality signals: has_price, has_images, has_rating, has_reviews, review_count_log
  - Popularity: product_age_days, is_in_stock, rating_value
  - Domain authority: domain_quality_score
- **Benefits**:
  - Batch retrieval: Fetch 1000 products in <50ms (columnar scan)
  - No computation overhead during search
  - Historical features available for analytics
  - Automatic updates on product recrawl

**Tier 2: Elasticsearch** (already exists)
- Already stores: product_name, description, brand, category, created_at
- Add fields: price, rating, review_count, availability
- Used for: BM25 candidate retrieval

**Tier 3: Real-time Computation** (in ML service)
- Query-document interaction features (cannot be precomputed)
- Examples: query-title exact match, BM25 score, query token overlap, brand match

---

### Phase 2: Updated Search Flow Architecture (New Data Flow)

```
┌─────────────────────────────────────────────────────────────────┐
│                    User Search Request                           │
│                 POST /api/products/search                        │
│                 {"query": "wireless headphones"}                 │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Pod                                     │
│  1. Query preprocessing (normalize, tokenize)                   │
│  2. Extract query features                                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Elasticsearch                                  │
│  - BM25 search on products index                                │
│  - Return top-N candidates (500-10,000)                         │
│  - Include: product_id, BM25 score, rank position              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Feature Extraction                              │
│                                                                  │
│  Parallel fetch:                                                │
│  ┌──────────────────────┬──────────────────────┐               │
│  │ ClickHouse           │ Elasticsearch        │               │
│  │ (precomputed         │ (product metadata    │               │
│  │  document features)  │  for interaction)    │               │
│  └──────────────────────┴──────────────────────┘               │
│                         │                                        │
│  Single ClickHouse query:                                       │
│  SELECT * FROM product_features                                 │
│  WHERE product_id IN (candidate_ids)                            │
│  → Returns 1000 rows in ~50ms                                   │
│                         │                                        │
│  Compute interaction features (query + doc)                     │
│  Build feature matrix: [N_candidates × N_features]             │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│               ML Ranking Service                                 │
│  - Load LightGBM/XGBoost model                                  │
│  - Predict relevance scores                                     │
│  - Return ranked candidate IDs + scores                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Pod                                     │
│  1. Sort by ML score                                            │
│  2. Take top-K (20-100)                                         │
│  3. Fetch full product details from PostgreSQL                 │
│  4. Return to user                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

### Phase 3: Latency Breakdown with ClickHouse (Target: <3s total)

| Step | Operation | Expected Latency | Notes |
|------|-----------|-----------------|-------|
| 1 | Query preprocessing | <5ms | Fast string operations |
| 2 | Elasticsearch query (1000 candidates) | 50-200ms | Current ES latency |
| 3 | **ClickHouse feature fetch** | **30-50ms** | **Single columnar query for 1000 products**|
| 4 | Interaction feature computation | 20-50ms | Query-document features only |
| 5 | ML inference (1000 candidates) | 50-150ms | LightGBM is fast |
| 6 | PostgreSQL fetch (top 20) | 10-50ms | Indexed query |
| **Total** | | **160-505ms** | **50% faster than before!** |

**Improvement over Redis approach**:
- **Before** (Redis cache): 100-300ms for feature extraction
- **After** (ClickHouse precomputed): 30-50ms + 20-50ms = 50-100ms
- **Speedup**: 2-3x faster feature extraction!

---

### Phase 4:  Infrastructure Costs (per region at 100% load)

| Component | Count | Monthly Cost | Notes |
|-----------|-------|-------------|-------|
| **ML Ranking Service** | 20-50 pods | $1,440 - $3,600 | 2 CPU, 4Gi RAM each @ $72/mo |
| **Model Storage (S3)** | - | $10 | <1GB models |
| **Elasticsearch (no change)** | 20 nodes | $40,000 | Already sized for search load |

**Total Additional Cost**: **$1,450 - $3,610 per region**

**4 Regions**: **$5,800 - $14,440/month**

**New Grand Total** (with ML ranking):
- Without ML: $785,840/month
- With ML: **$791,640 - $800,280/month** (~1-2% increase)

---

## Summary

### Benefits of ML Ranking with ClickHouse Precomputation

1. Better relevance: Personalized to user intent, learning from implicit feedback
2. Flexible: Easy to add new features (price range, popularity, freshness)
3. Scalable: LightGBM inference is fast (under 150ms for 1000 candidates)
4. Iterative improvement: Continuously improve via retraining
5. Fast feature retrieval: ClickHouse columnar storage enables 30-50ms batch fetch for 1000 products
6. Zero search-time computation: Document features precomputed during parsing
7. Automatic freshness: Features updated on every product recrawl

---

## References

- [SCALE_ARCHITECTURE_DECISIONS.md](SCALE_ARCHITECTURE_DECISIONS.md)
- [SCALE_ARCHITECTURE_DIAGRAM.md](SCALE_ARCHITECTURE_DIAGRAM.md)
- [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)
