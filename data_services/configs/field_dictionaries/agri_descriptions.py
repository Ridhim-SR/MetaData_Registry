# Column descriptions for agri_dept (distribution + scheme) and the missing
# farmers columns, written in the exact shape ai_metadata.write_csv() emits:
# name, business_description, tag.  Only field names and types were used as
# the source -- never records.
#
# tag: a value from ai_metadata.KNOWN_TAGS (Financial, Firm/Contractor-
# Identifier, Geospatial, Status/Workflow, Date/Timestamp), or "" to leave
# curate's auto-tagger in charge.  "" is the default on purpose: it only
# makes sense to set a tag here when this list knows something the name
# rules in curate.AUTO_TAG_RULES do not.

# table_id suffix -> {column name: (business_description, proposed tag)}
DESCRIPTIONS = {
    # ------------------------------------------------------------------
    # distribution_record_dataset
    # ------------------------------------------------------------------
    "crop_sales": {
        "id": ("Unique row identifier for this crop sale record.", ""),
        "status": ("Lifecycle status of the record (open, closed or cancelled).", "Status/Workflow"),
        "block_code": ("Administrative block code where the sale was recorded.", ""),
        "central_subsidy": ("Central government subsidy amount on this sale.", "Financial"),
        "crop_id": ("Identifier of the crop that was sold.", ""),
        "cumulative_sale": ("Running total held against this record; whether it measures "
                            "quantity or value is not stated by the field name.", ""),
        "device_id": ("Identifier of the device used to enter the record.", ""),
        "device_user_name": ("User name of the person who entered the record on the device.", ""),
        "dist_code": ("District code of the location where the sale was recorded.", ""),
        "distribution_type": ("Type of distribution route used for this crop sale.", ""),
        "farmer_share": ("Share of the sale amount payable to the farmer.", "Financial"),
        "mausam_id": ("Season reference taken from the Mausam source system; the exact "
                      "meaning is not stated by the field name.", ""),
        "prajati_id": ("Reference to the prajati (crop variety or class); the exact meaning "
                       "is not stated by the field name.", ""),
        "quantity": ("Quantity of crop sold under this record.", ""),
        "receipt_no": ("Receipt number issued for the sale.", ""),
        "registration_id": ("Registration reference linked to this sale record.", ""),
        "sales_date": ("Date on which the sale was recorded.", "Date/Timestamp"),
        "sell_price": ("Price at which the crop was sold.", "Financial"),
        "state_subsidy": ("State government subsidy amount on this sale.", "Financial"),
        "store_id": ("Identifier of the store or centre holding the stock.", ""),
        "trans_mode": ("Mode of transport used for the transaction.", ""),
        "transaction_no": ("Transaction number of the sale.", "Financial"),
        "transaction_type": ("Type of transaction recorded for the sale.", "Financial"),
        "year_id": ("Financial or crop year this sale belongs to.", ""),
        "consume_land": ("Land area recorded as consumed for this crop; the unit is not "
                         "stated by the field name.", ""),
        "remaining_land": ("Land area recorded as remaining for this crop; the unit is not "
                           "stated by the field name.", ""),
        "total_land": ("Total land area recorded for this crop; the unit is not stated by "
                       "the field name.", ""),
        "batch_number": ("Batch number of the stock issued or sold.", ""),
        "caste_id": ("Caste category reference of the beneficiary.", ""),
        "bill_number": ("Number of the bill raised for this sale.", "Financial"),
        "master_store_id": ("Identifier of the parent or master store.", ""),
        "departmental_scheme_id": ("Identifier of the departmental scheme funding this sale.", ""),
        "departmental_scheme_name": ("Name of the departmental scheme funding this sale.", ""),
        "agency_id": ("Identifier of the agency that executed the sale or distribution.", ""),
        "subsidy_from_top_up_project": ("Subsidy received from the top-up project on this sale.", "Financial"),
        "top_up_scheme_id": ("Identifier of the top-up scheme applied to this sale.", ""),
        "top_up_scheme_name": ("Name of the top-up scheme applied to this sale.", ""),
        "top_up_max_subsidy_amount": ("Maximum subsidy amount allowed under the top-up scheme.", "Financial"),
        "top_up_max_subsidy_percentage": ("Maximum subsidy percentage allowed under the top-up scheme.", "Financial"),
        "bill_type": ("Type of bill raised for this sale.", ""),
        "store_type": ("Type of store or centre the stock belongs to.", ""),
        "cafeteria_id": ("Identifier of the cafeteria associated with the sale.", ""),
        "bill_upload": ("Reference to the bill document uploaded for this sale.", ""),
        "change_mainschemeid": ("Identifier of the main scheme after a scheme change; the "
                                "field name appears to be missing an underscore.", ""),
        "unit_name": ("Name of the unit or centre the sale is recorded against.", ""),
        "unit_id": ("Identifier of the unit or centre the sale is recorded against.", ""),
        "updated_departmental_scheme_id": ("Updated identifier of the departmental scheme after a correction.", ""),
        "updated_departmental_scheme_name": ("Updated name of the departmental scheme after a correction.", ""),
        "updated_top_up_scheme_id": ("Updated identifier of the top-up scheme after a correction.", ""),
        "updated_top_up_scheme_name": ("Updated name of the top-up scheme after a correction.", ""),
        "modified_by": ("User who last modified the record.", ""),
        "modified_at": ("Timestamp when the record was last modified.", "Date/Timestamp"),
        "previous_central_subsidy": ("Central subsidy amount applied before the current revision.", "Financial"),
    },

    "current_booking": {
        "id": ("Unique row identifier for this booking.", ""),
        "created_at": ("Timestamp when the record was created.", "Date/Timestamp"),
        "created_by": ("User who created the record.", ""),
        "modified_at": ("Timestamp when the record was last modified.", "Date/Timestamp"),
        "modified_by": ("User who last modified the record.", ""),
        "status": ("Lifecycle status of the booking.", "Status/Workflow"),
        "applicable_subsidy": ("Subsidy amount applicable to this booking.", "Financial"),
        "booking_amount": ("Amount booked for this transaction.", "Financial"),
        "booking_date": ("Date on which the booking was made.", "Date/Timestamp"),
        "bookings_id": ("Reference to the parent booking record.", ""),
        "bookings_status": ("Status of the booking in the booking workflow.", "Status/Workflow"),
        "payment_mode": ("Mode of payment used for the booking.", "Financial"),
        "transaction_id": ("Identifier of the payment transaction for the booking.", "Financial"),
        "waiting_no": ("Waiting number assigned to the booking in the queue.", ""),
        "crop_noncrop_name_id": ("Identifier of the crop or non-crop item booked.", ""),
        "departmental_scheme_id": ("Identifier of the departmental scheme under which the booking was made.", ""),
        "online_booking_details_id": ("Reference to the detail row of the online booking.", ""),
        "online_booking_id": ("Reference to the online booking this row belongs to.", ""),
        "variety_id": ("Identifier of the crop variety booked.", ""),
        "payment_term": ("Payment term agreed for the booking.", "Financial"),
        "grant_id": ("Identifier of the grant linked to this booking.", "Financial"),
        "booking_person": ("Person count the booking was made for; it may instead be a "
                           "person identifier, which the name alone does not settle.", ""),
        "sub_assistance_id": ("Identifier of the subsidy assistance component linked to the booking.", ""),
        "payment_status": ("Payment status of the booking.", "Status/Workflow"),
        "document_upload_validity": ("Validity period of the uploaded document, in days.", ""),
        "financial_year_id": ("Identifier of the financial year the booking belongs to.", ""),
        "winning_date": ("Date on which the booking won allocation in the draw.", "Date/Timestamp"),
        "cancel_date": ("Date on which the booking was cancelled.", "Date/Timestamp"),
        "sequence_no": ("Sequence number of the booking in processing order.", ""),
        "booking_level": ("Level at which the booking is made, for example state, district or block.", ""),
        "is_scheme_validation_available": ("Whether scheme validation is available for this booking.", ""),
        "block_name": ("Name of the administrative block.", ""),
        "district_name": ("Name of the district.", ""),
        "way_of_booking": ("Channel through which the booking was made.", ""),
        "block_id": ("Identifier of the administrative block.", ""),
        "district_id": ("Identifier of the district.", ""),
        "village_id": ("Identifier of the village.", ""),
        "temp_column": ("Temporary working column; no documented purpose.", ""),
        "repayment_date": ("Date on which the repayment fell due.", "Date/Timestamp"),
        "repayment_amount": ("Amount to be repaid for this booking.", "Financial"),
        "repayment_mode": ("Mode of repayment used.", "Financial"),
        "repayment_transaction_id": ("Identifier of the repayment transaction.", "Financial"),
        "old_grant_id": ("Previous grant identifier retained for migration reference.", "Financial"),
        "old_online_booking_details_id": ("Previous detail-row identifier retained for migration reference.", ""),
        "old_online_booking_id": ("Previous online booking identifier retained for migration reference.", ""),
        "old83_grant_id": ("Grant identifier carried over from the previous system; the "
                           "\"83\" prefix is not explained by the field name.", "Financial"),
        "old83_online_booking_id": ("Online booking identifier carried over from the previous system.", ""),
        "old83_online_booking_details_id": ("Detail-row identifier carried over from the previous system.", ""),
        "revert83to11": ("Flag marking a record reverted between system versions; the exact "
                         "meaning is not stated by the field name.", ""),
        "updatewating_status": ("Updated waiting-list status of the booking; the field name "
                                "appears to be a typo of update_waiting_status.", "Status/Workflow"),
        "old_wating_no": ("Previous waiting number retained from the earlier system; the "
                          "field name appears to be a typo of old_waiting_no.", ""),
        "old_bookings_status": ("Previous booking status retained from the earlier system.", "Status/Workflow"),
        "cancel_booking_flag": ("Whether the booking has been cancelled.", ""),
        "promote_booking_flag": ("Whether the booking was promoted off the waiting list.", ""),
        "isp_mandal_code": ("Mandal (tehsil) code of the ISP office handling the booking.", ""),
    },

    "current_booking_farmer_details": {
        "id": ("Unique row identifier for this farmer booking detail.", ""),
        "created_at": ("Timestamp when the record was created.", "Date/Timestamp"),
        "created_by": ("User who created the record.", ""),
        "modified_at": ("Timestamp when the record was last modified.", "Date/Timestamp"),
        "modified_by": ("User who last modified the record.", ""),
        "status": ("Lifecycle status of the record.", "Status/Workflow"),
        "address": ("Residential address of the farmer.", ""),
        "caste": ("Caste category of the farmer.", ""),
        "email_id": ("Email address of the farmer.", ""),
        "farmer_name": ("Full name of the farmer who made the booking.", ""),
        "father_name": ("Father's name of the farmer.", ""),
        "mobile_no": ("Mobile number of the farmer.", ""),
        "registration_no": ("Farmer registration number linked to this booking.", ""),
        "current_booking_id": ("Reference to the booking this farmer detail belongs to.", ""),
        "farmer_id": ("Identifier of the farmer this detail belongs to.", ""),
        "sanstha_type_id": ("Type of the sanstha (institution) the farmer belongs to.", ""),
        "sansthaname": ("Name of the sanstha (institution) the farmer belongs to.", ""),
        "sanstha_id": ("Identifier of the sanstha (institution) the farmer belongs to.", ""),
        "beneficiary_category_id": ("Beneficiary category of the farmer.", ""),
    },

    "online_booking": {
        "id": ("Unique row identifier for the online booking window.", ""),
        "created_at": ("Timestamp when the record was created.", "Date/Timestamp"),
        "created_by": ("User who created the record.", ""),
        "modified_at": ("Timestamp when the record was last modified.", "Date/Timestamp"),
        "modified_by": ("User who last modified the record.", ""),
        "status": ("Lifecycle status of the booking window.", "Status/Workflow"),
        "end_date": ("End date of the online booking window.", "Date/Timestamp"),
        "maxno_booking_allowed_within_fy_in_selected_scheme": (
            "Maximum number of bookings allowed in the financial year under the selected scheme.", ""),
        "start_date": ("Start date of the online booking window.", "Date/Timestamp"),
        "way_of_booking_type": ("Type of channel used for the online booking.", ""),
        "financial_year_id": ("Identifier of the financial year the booking window belongs to.", ""),
        "booking_level": ("Level at which the booking window applies, for example state, district or block.", ""),
        "booking_round": ("Round number of the booking window.", ""),
    },

    "online_booking_details": {
        "id": ("Unique row identifier for this online booking detail.", ""),
        "created_at": ("Timestamp when the record was created.", "Date/Timestamp"),
        "created_by": ("User who created the record.", ""),
        "modified_at": ("Timestamp when the record was last modified.", "Date/Timestamp"),
        "modified_by": ("User who last modified the record.", ""),
        "status": ("Lifecycle status of the detail row.", "Status/Workflow"),
        "booking_amount": ("Amount booked on this online booking.", "Financial"),
        "booking_amount_required": ("Whether a booking amount must be paid for this item.", "Financial"),
        "maxno_booking_allowed": ("Maximum number of bookings allowed for this item.", ""),
        "repurchase_threshold": ("Stock level at which repurchase of the item is triggered.", ""),
        "restrict_maxno_booking": ("Whether the maximum number of bookings is restricted.", ""),
        "total_non_crop_distributed": ("Total quantity of non-crop items distributed.", ""),
        "upload_document": ("Reference to the document uploaded with the booking.", ""),
        "crop_noncrop_name_id": ("Identifier of the crop or non-crop item in the booking.", ""),
        "online_booking_id": ("Reference to the online booking this detail row belongs to.", ""),
        "sub_assistance_id": ("Identifier of the subsidy assistance component linked to the item.", ""),
        "grant_id": ("Identifier of the grant linked to this booking.", "Financial"),
        "total_booking_allowed": ("Total number of bookings allowed for this item.", ""),
        "document_upload_validity": ("Validity period of the uploaded document, in days.", ""),
    },

    # ------------------------------------------------------------------
    # scheme_physical_financial_progress_dataset
    # ------------------------------------------------------------------
    "financial_budget_allocation": {
        "id": ("Unique row identifier for this budget allocation.", ""),
        "created_at": ("Timestamp when the record was created.", "Date/Timestamp"),
        "created_by": ("User who created the record.", ""),
        "modified_at": ("Timestamp when the record was last modified.", "Date/Timestamp"),
        "modified_by": ("User who last modified the record.", ""),
        "status": ("Lifecycle status of the allocation.", "Status/Workflow"),
        "allocation_type": ("Type of budget allocation recorded.", "Financial"),
        "assign_by": ("Identifier of the officer who assigned the allocation.", ""),
        "assign_to": ("Identifier of the officer the allocation was assigned to.", ""),
        "project_budget_amount": ("Budget allocated to the project.", "Financial"),
        "project_remaining_amount": ("Budget remaining unspent against the project.", "Financial"),
        "recent_received_sanction_amount": ("Sanction amount received most recently.", "Financial"),
        "total_cumulative_sanction_amount": ("Total sanction amount accumulated to date.", "Financial"),
        "departmental_scheme_id": ("Identifier of the departmental scheme the budget belongs to.", ""),
        "financial_year_id": ("Identifier of the financial year the allocation belongs to.", ""),
        "office_type_id": ("Type of office the allocation was made to.", ""),
        "parent_id": ("Identifier of the parent record in the allocation hierarchy.", ""),
        "umbrella_scheme_id": ("Identifier of the umbrella scheme the allocation rolls up into.", ""),
    },

    "grant_wise_bill_generation": {
        "id": ("Unique row identifier for this grant-wise bill.", ""),
        "created_at": ("Timestamp when the record was created.", "Date/Timestamp"),
        "created_by": ("User who created the record.", ""),
        "modified_at": ("Timestamp when the record was last modified.", "Date/Timestamp"),
        "modified_by": ("User who last modified the record.", ""),
        "status": ("Lifecycle status of the bill.", "Status/Workflow"),
        "action_status": ("Action status of the bill generation workflow.", "Status/Workflow"),
        "beneficiary_id": ("Identifier of the beneficiary the bill is raised for.", ""),
        "district_id": ("Identifier of the district the bill belongs to.", ""),
        "farmer_id": ("Identifier of the farmer the bill is raised for.", ""),
        "farmer_name": ("Full name of the farmer the bill is raised for.", ""),
        "father_name": ("Father's name of the farmer.", ""),
        "funding_pattern_id": ("Funding pattern applied to the grant.", "Financial"),
        "record_id": ("Identifier of the record this bill belongs to.", ""),
        "record_type": ("Type of record this bill belongs to.", ""),
        "record_type_id": ("Numeric code for the type of record.", ""),
        "beneficiary_category_id": ("Beneficiary category of the person the bill is raised for.", ""),
        "departmental_scheme_id": ("Identifier of the departmental scheme the grant belongs to.", ""),
        "grant_id": ("Identifier of the grant the bill is raised against.", "Financial"),
        "email_id": ("Email address of the beneficiary or vendor.", ""),
        "mobile_no": ("Mobile number of the beneficiary or vendor.", ""),
        "registration_no": ("Registration number of the beneficiary or vendor.", ""),
        "vendor_address": ("Address of the vendor the bill is raised to.", ""),
        "vendor_name": ("Name of the vendor the bill is raised to.", ""),
        "vendor_registration_id": ("Registration reference of the vendor.", ""),
        "dbt_date": ("Date on which the direct benefit transfer was made.", "Date/Timestamp"),
        "dbt_no": ("Direct benefit transfer transaction number.", ""),
        "loan_bank_name": ("Name of the bank that disbursed the loan.", ""),
        "loan_branch_name": ("Name of the bank branch that disbursed the loan.", ""),
        "loan_ifsc": ("IFSC code of the bank branch holding the loan account.", "Financial"),
        "loan_account_no": ("Bank account number the loan is held against.", "Financial"),
        "iswithloan": ("Whether the grant is linked to a loan.", "Financial"),
        "office_type_id": ("Type of office the bill was generated for.", ""),
        "unit_id": ("Identifier of the unit or centre the bill belongs to.", ""),
        "role_id": ("Identifier of the officer role that acted on the bill.", ""),
        "financial_year_id": ("Identifier of the financial year the bill belongs to.", ""),
    },

    "target_allocation_v2": {
        "id": ("Unique row identifier for this target allocation.", ""),
        "created_at": ("Timestamp when the record was created.", "Date/Timestamp"),
        "created_by": ("User who created the record.", ""),
        "modified_at": ("Timestamp when the record was last modified.", "Date/Timestamp"),
        "modified_by": ("User who last modified the record.", ""),
        "status": ("Lifecycle status of the target.", "Status/Workflow"),
        "allocation_date": ("Date on which the allocation was made.", "Date/Timestamp"),
        "allocation_type": ("Type of allocation recorded.", "Financial"),
        "assign_by": ("Identifier of the officer who assigned the target.", ""),
        "assign_to": ("Identifier of the officer the target was assigned to.", ""),
        "project_budget_amount": ("Budget allocated against the target.", "Financial"),
        "project_remaining_amount": ("Budget remaining unspent against the target.", "Financial"),
        "total_hysical": ("Total physical progress recorded; the field name appears to be a "
                          "typo of total_physical.", ""),
        "departmental_scheme_id": ("Identifier of the departmental scheme the target belongs to.", ""),
        "financial_year_id": ("Identifier of the financial year the target belongs to.", ""),
        "module_type_id": ("Type of module the allocation was created under.", ""),
        "office_type_id": ("Type of office the target was assigned to.", ""),
        "parent_id": ("Identifier of the parent record in the allocation hierarchy.", ""),
        "umbrella_scheme_id": ("Identifier of the umbrella scheme the target rolls up into.", ""),
        "district_id": ("Identifier of the district the target is allocated for.", ""),
        "booking_level": ("Level at which the target applies, for example state, district or block.", ""),
        "store_type_id": ("Type of store the target applies to.", ""),
    },

    # ------------------------------------------------------------------
    # farmer_registration_master_dataset -- only the columns that have no
    # description yet; the department's own 18 answers are left untouched.
    # ------------------------------------------------------------------
    "farmers": {
        "id": ("Unique row identifier for the farmer record.", ""),
        "created_at": ("Timestamp when the record was created.", "Date/Timestamp"),
        "created_by": ("User who created the record.", ""),
        "modified_at": ("Timestamp when the record was last modified.", "Date/Timestamp"),
        "modified_by": ("User who last modified the record.", ""),
        "status": ("Lifecycle status of the farmer record.", "Status/Workflow"),
        "hindi_address": ("Residential address of the farmer, as recorded in Hindi.", ""),
        "hindi_father_name": ("Father's name of the farmer, as recorded in Hindi.", ""),
        "hindi_name": ("Name of the farmer, as recorded in Hindi.", ""),
        "mobile_verified": ("Whether the farmer's mobile number has been verified.", ""),
        "aadhar_response": ("Response text returned by the Aadhaar verification check.", ""),
        "submission_date": ("Date on which the farmer's application was submitted.", "Date/Timestamp"),
        "block_name": ("Name of the administrative block the farmer belongs to.", ""),
        "pin_code": ("Postal PIN code of the farmer's address.", ""),
        "uu_id": ("Unique identifier issued for the record; the issuing system is not "
                  "stated by the field name.", ""),
        "benficiary_categories_id": ("Beneficiary category reference; the field name appears "
                                     "to be a typo of beneficiary_categories_id.", ""),
        "f_id": ("Identifier whose meaning is not stated by the field name; possibly a form "
                 "or farmer reference.", ""),
        "sr_no": ("Serial number of the record.", ""),
        "caste_application_no": ("Application number of the farmer's caste certificate.", ""),
        "caste_date_of_issue": ("Date on which the farmer's caste certificate was issued.", "Date/Timestamp"),
        "caste_id": ("Caste category reference of the farmer.", ""),
        "bank_id": ("Identifier of the bank holding the farmer's account.", ""),
        "bank_name": ("Name of the bank holding the farmer's account.", ""),
        "branch_id": ("Identifier of the bank branch holding the farmer's account.", ""),
        "branch_name": ("Name of the bank branch holding the farmer's account.", ""),
        "bank_district_id": ("Identifier of the district where the bank branch is located.", ""),
        "bank_district_name": ("District where the bank branch is located.", ""),
        "district": ("District the farmer belongs to.", ""),
        "isp_request_id": ("Identifier of the request raised with the ISP (service provider) system.", ""),
        "isp_applicant_id": ("Identifier of the applicant in the ISP (service provider) system.", ""),
        "isp_service_code": ("Service code requested from the ISP (service provider) system.", ""),
        "token": ("Access or session token for the record; the exact purpose is not stated "
                  "by the field name.", ""),
        "ddo_beneficiary_creation_id": ("Identifier of the beneficiary creation entry made by the "
                                        "DDO (Drawing and Disbursing Officer).", ""),
        "sna_beneficiary_creation_id": ("Identifier of the beneficiary creation entry made by the "
                                        "SNA (Single Nodal Agency).", ""),
        "adhar_reference_no": ("Reference number returned by the Aadhaar verification check.", ""),
    },
}

# Suggested dataset-level values for catalog.yaml (what ai_metadata prints).
DATASETS = {
    "agri_dept.distribution_record_dataset": (
        "CAT-3",
        "Crop sale and booking records for the department's distribution schemes: crop "
        "sales with central and state subsidy (crop_sales), farmer bookings and their "
        "repayment schedule (current_booking and its farmer details), and the online "
        "booking windows that govern how many bookings a crop or item may receive.",
        "Holds named individual farmers with address, caste, mobile and email alongside "
        "booking and repayment amounts.",
    ),
    "agri_dept.farmer_registration_master_dataset": (
        "CAT-3",
        "Master record of registered farmers: identity and contact details, caste and "
        "certificate references, Aadhaar verification status, land and scheme eligibility, "
        "and the bank account used for direct benefit transfers.",
        "Holds Aadhaar numbers, date of birth, address, caste and bank account details.",
    ),
    "agri_dept.scheme_physical_financial_progress_dataset": (
        "CAT-3",
        "Physical and financial progress of departmental schemes: target allocations "
        "against each scheme, budgets received and still unspent, and grant-wise bills "
        "raised for farmers and vendors including their loan and direct benefit transfer "
        "details.",
        "Holds named beneficiaries and vendors with mobile, email and bank account details "
        "against sanctioned amounts.",
    ),
    "rural_development_department.mgnrega": (
        "CAT-1",
        "Gram Panchayat-level MGNREGA implementation data from the Ministry of Rural "
        "Development's MIS: job-card registration and workers by social category, "
        "employment demanded and offered with persondays, women's bank-account coverage, "
        "and works, expenditure and persondays by work type.",
        "Aggregated counts by state, district, block and gram panchayat only -- no "
        "individual-level rows and no direct identifiers.",
    ),
}
