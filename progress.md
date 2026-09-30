# Project Progress: Agriculture Department Datasets

## Status: Complete (Storage + OpenMetadata)

### Department
- **Department**: Agriculture Department (agriculture_department)
- **Branch**: `department/agriculture_department/distribution_record_dataset`
  (all 3 datasets live on this one branch)

---

### Dataset 1: Distribution Record Dataset
- **Dataset**: DISTRIBUTION RECORD DATASET (distribution_record_dataset)

#### Tables Published (5/5)

| Table | Columns | OpenMetadata FQN |
|-------|---------|------------------|
| crop_sales | 53 | agriculture_department.distribution_record_dataset.public.crop_sales |
| current_booking | 55 | agriculture_department.distribution_record_dataset.public.current_booking |
| current_booking_farmer_details | 19 | agriculture_department.distribution_record_dataset.public.current_booking_farmer_details |
| online_booking | 13 | agriculture_department.distribution_record_dataset.public.online_booking |
| online_booking_details | 19 | agriculture_department.distribution_record_dataset.public.online_booking_details |

#### Source Files Added
- data_services/source/distribution_records/*.csv (5 files)
- data_services/configs/distribution_records_manifest.csv

#### Preprocessing (new, `data_services/scripts/`)
Multi-table CSV sources are split/cleaned into per-table column-definition
files before the batch run:
```bash
python -m scripts.preprocess_dataset --dataset <slug> --dry-run
python -m scripts.preprocess_dataset --all
```
- `scripts/preprocessors/base.py` — shared interface
- `scripts/preprocessors/multi_table_csv.py` — header/section splitting
- `scripts/preprocessors/registry.py` — per-dataset config + manifest generation

---

### Dataset 2: Farmer Registration Master Dataset
- **Dataset**: FARMER REGISTRATION MASTER DATASET (farmer_registration_master_dataset)

#### Tables Published (1/1)

| Table | Columns | OpenMetadata FQN |
|-------|---------|------------------|
| farmers | 53 | agriculture_department.farmer_registration_master_dataset.public.farmers |

#### Source Files Added
- data_services/source/farmer_registration/farmers.csv
- data_services/configs/farmer_registration_master_dataset_manifest.csv

---

### Dataset 3: Scheme Physical Financial Progress Dataset
- **Dataset**: SCHEME PHYSICAL FINANCIAL PROGRESS DATASET (scheme_physical_financial_progress_dataset)

#### Tables Published (3/3)

| Table | Columns | OpenMetadata FQN |
|-------|---------|------------------|
| target_allocation_v2 | 22 | agriculture_department.scheme_physical_financial_progress_dataset.public.target_allocation_v2 |
| financial_budget_allocation | 18 | agriculture_department.scheme_physical_financial_progress_dataset.public.financial_budget_allocation |
| grant_wise_bill_generation | 36 | agriculture_department.scheme_physical_financial_progress_dataset.public.grant_wise_bill_generation |

#### Source Files Added
- data_services/source/scheme_progress/target_allocation_v2.csv
- data_services/source/scheme_progress/financial_budget_allocation.csv
- data_services/source/scheme_progress/grant_wise_bill_generation.csv
- data_services/configs/scheme_physical_financial_progress_dataset_manifest.csv

---

### Pipeline Commands

Register department:
```bash
DEPARTMENT_ID=agriculture_department DEPARTMENT_NAME="Agriculture Department" python -m src.schema_registry.lookups
```

Batch ingest (storage):
```bash
MANIFEST_FILE=configs/distribution_records_manifest.csv python -m src.schema_registry.batch
MANIFEST_FILE=configs/farmer_registration_master_dataset_manifest.csv python -m src.schema_registry.batch
MANIFEST_FILE=configs/scheme_physical_financial_progress_dataset_manifest.csv python -m src.schema_registry.batch
```

Batch ingest + OpenMetadata:
```bash
OPENMETADATA_JWT_TOKEN=<token> MANIFEST_FILE=configs/distribution_records_manifest.csv python -m src.schema_registry.batch
OPENMETADATA_JWT_TOKEN=<token> MANIFEST_FILE=configs/farmer_registration_master_dataset_manifest.csv python -m src.schema_registry.batch
OPENMETADATA_JWT_TOKEN=<token> MANIFEST_FILE=configs/scheme_physical_financial_progress_dataset_manifest.csv python -m src.schema_registry.batch
```

---

### Field-Level Classification (MDSF)
Per MDSF, classification is done **per field**, not per dataset — based on
potential risk of disclosure, re-identification or misuse.

- Levels: `Public`, `Internal`, `Confidential`, `Restricted`, `PII`, `Financial`, `Health`
- Auto-classified by rules in `src/schema_registry/curate.py` (`AUTO_CLASSIFICATION_RULES`)
- Manual override via field dictionary CSV (extra `classification` column), wired
  through the manifest's `business_metadata_file` field
- Priority: field dictionary > auto-classification > default (`Internal`)
- Sample field dictionary: `data_services/configs/field_dictionaries/farmer_registration_field_dictionary.csv`

Field Dictionary CSV format:
```csv
name,business_description,tag,glossary_term,active,classification
aadhar_no,"Unique Aadhaar number",PII,UIDAI_Aadhaar,true,PII
```

#### Published to OpenMetadata as column tags (done 2026-09-30)
Each curated column's `classification` is now applied as a tag on that column:

- Tag classification `MDSF` (mutually exclusive) auto-created by
  `openmetadata_publish._ensure_classification()` with all 7 level tags —
  idempotent, runs once per publish
- `openmetadata_publish._to_column()` attaches a `TagLabel`
  (`source=Classification`, `labelType=Manual`, `state=Confirmed`) for the
  row's `classification`
- Verified: **288/288 columns tagged** across all 9 tables
  (`MDSF.Internal` 189, `MDSF.PII` 55, `MDSF.Financial` 41,
  `MDSF.Public` 2, `MDSF.Restricted` 1)

> **Gotcha:** OM 2.0.2 only populates `columns[].tags` when the request asks
> for **both** fields — `?fields=tags,columns`. `?fields=tags` alone returns
> an empty array (see `TableRepository` line ~210:
> `fields.contains(COLUMN_FIELD) && fields.contains(FIELD_TAGS)`).

---

### OpenMetadata Environment
- UI/API: http://localhost:8585 (Docker Compose: `infrastructure/openmetadata/`)
- Admin login: `admin@open-metadata.org` / `admin`
- JWT token for pipelines: **ingestion-bot** token (never expires) —
  Settings → Bots → ingestion-bot → Authentication Configuration, or decrypt
  from DB using `FERNET_KEY` in docker-compose
- 2026-09-30: MySQL volume was corrupted (InnoDB signal 6 crash loop) and reset;
  `docker-volume/db-data` wiped, migrations re-ran, all 9 tables re-published
- 2026-09-30: the reset left **5 orphaned Elasticsearch table docs** (old UUIDs
  that no longer existed in MySQL), so the Explore UI showed 14 tables instead
  of 9. Deleted them from `table_search_index`; API and UI both report 9 now.
  → If MySQL is ever wiped again, clean ES too (or re-run the search indexer).
- `bytea` type added to `_TYPE_MAP` (openmetadata_publish.py) and
  `KNOWN_POSTGRES_TYPES` (curate.py)

---

### Tests
- `python -m pytest tests/ -q` → **66 passed, 1 failed**
- The 1 failure is pre-existing and unrelated:
  `test_ddl_parser.py::test_real_vishwakarma_sample_parses_all_213_columns`
  needs `samples/pwd_vishwakarma_full_raw_columns.txt`, which is gitignored
  (raw production dumps). Not a regression.

---

### Future Work
- [ ] Add Field Dictionary (business metadata) for remaining tables
- [ ] Add dataset governance fields (owner, retention_policy, lineage)
- [ ] Add new tables as they arrive
- [x] Publish field-level classifications as OpenMetadata tags/taxonomy