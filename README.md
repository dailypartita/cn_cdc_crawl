# China CDC Sentinel Hospital Surveillance Data

[![Data](https://img.shields.io/badge/Data-CSV-brightgreen.svg)]()
[![Update](https://img.shields.io/badge/Update-Weekly-blue.svg)]()

Curated surveillance data from China CDC sentinel hospitals. Data is provided in CSV format and updated weekly for respiratory disease monitoring and epidemiological forecasting.

## Data Files

### COVID-19 Surveillance
**File:** `data/cncdc_surveillance_covid19.csv`

Weekly COVID-19 surveillance data formatted for the [China-COVID-19-Forecast-Hub](https://github.com/dailypartita/China-COVID-19-Forecast-Hub) project.

**Columns:**
- `reference_date` - Surveillance week start (Monday)
- `target_end_date` - Surveillance week end (Sunday)  
- `report_week` - ISO week number
- `pathogen` - Pathogen name (SARS-CoV-2)
- `ili_percent` - Outpatient ILI positive rate (%)
- `sari_percent` - Inpatient SARI positive rate (%)

### Comprehensive Respiratory Surveillance
**File:** `data/cncdc_surveillance_all.csv`

Multi-pathogen surveillance data including COVID-19, influenza, RSV, and other respiratory pathogens.

**Columns:**
- `report_date` - Report publication date
- `report_week` - ISO week number
- `pathogen` - Pathogen name
- `ili_percent` - Outpatient ILI positive rate (%)
- `sari_percent` - Inpatient SARI positive rate (%)

**Pathogens monitored:** SARS-CoV-2, Influenza A/B, RSV, Adenovirus, hMPV, PIV, Common Coronaviruses, Bocavirus, Rhinovirus, Enterovirus, Mycoplasma pneumoniae.

## Notes

⚠️ **2025 Weeks 14-22:** Data for these weeks was published in monthly reports. Only COVID-19 data is available for this period (see `data/cncdc_suverillance_2025_14_22.csv`).

## Data Source

Official surveillance reports from the Chinese Center for Disease Control and Prevention (China CDC). Data is automatically extracted and updated every Sunday.

## Contact

Email: yang_kaixin@gzlab.ac.cn

## Disclaimer

Data is provided for research and analysis purposes. Users should verify data quality and appropriateness for their specific use case.
