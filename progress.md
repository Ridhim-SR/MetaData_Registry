# Project Progress: Distribution Records Dataset

## Status: Complete (Storage + OpenMetadata)

### Dataset Info
- **Department**: Agriculture Department (agriculture_department)
- **Dataset**: DISTRIBUTION RECORD DATASET (distribution_record_dataset)
- **Branch**: department/agriculture_department/distribution_record_dataset

### Tables Published (5/5)

| Table | Columns | OpenMetadata FQN |
|-------|---------|------------------|
| crop_sales | 53 | agriculture_department.distribution_record_dataset.public.crop_sales |
| current_booking | 55 | agriculture_department.distribution_record_dataset.public.current_booking |
| current_booking_farmer_details | 19 | agriculture_department.distribution_record_dataset.public.current_booking_farmer_details |
| online_booking | 13 | agriculture_department.distribution_record_dataset.public.online_booking |
| online_booking_details | 19 | agriculture_department.distribution_record_dataset.public.online_booking_details |

### Source Files Added
- data_services/source/distribution_records/*.csv (5 files)
- data_services/configs/distribution_records_manifest.csv

### Pipeline Commands
Register department:
DEPARTMENT_ID=agriculture_department DEPARTMENT_NAME=Agriculture Department python -m src.schema_registry.lookups

Batch ingest (storage):
MANIFEST_FILE=configs/distribution_records_manifest.csv python -m src.schema_registry.batch

Batch ingest + OpenMetadata:
OPENMETADATA_JWT_TOKEN=<token> MANIFEST_FILE=configs/distribution_records_manifest.csv python -m src.schema_registry.batch

### Auto-Tagging Applied
- Date/Timestamp: *_date, *_at columns
- Financial: *_amount, *_price, *_subsidy columns
- Identifier: *_id, *_code columns

### Future Work
- [ ] Add Field Dictionary (business metadata) when available
- [ ] Add dataset governance fields (owner, retention_policy, lineage)
- [ ] Add new tables as they arrive
