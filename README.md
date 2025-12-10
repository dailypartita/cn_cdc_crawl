# China CDC Sentinel Hospital Surveillance Data

[![Data](https://img.shields.io/badge/Data-CSV-brightgreen.svg)]()
[![Update](https://img.shields.io/badge/Update-Weekly-blue.svg)]()

Structured surveillance data from China CDC sentinel hospitals, provided in CSV format. Data is automatically updated weekly for respiratory disease monitoring and forecasting.

## About

This repository provides processed surveillance data from the Chinese Center for Disease Control and Prevention (China CDC), covering:

- **COVID-19 surveillance** - SARS-CoV-2 monitoring reports
- **Respiratory disease surveillance** - Multi-pathogen sentinel monitoring

Data supports the [China-COVID-19-Forecast-Hub](https://github.com/dailypartita/China-COVID-19-Forecast-Hub) project.

## Data Files

### COVID-19 Surveillance Data
**File:** `data/cncdc_surveillance_covid19.csv`

Columns:
- `reference_date`: Surveillance week start date (Monday)
- `target_end_date`: Surveillance week end date (Sunday)
- `report_week`: Annual reporting week number
- `pathogen`: Pathogen name (SARS-CoV-2)
- `ili_percent`: ILI positive rate (%)
- `sari_percent`: SARI positive rate (%)

### Comprehensive Surveillance Data
**File:** `data/cncdc_surveillance_all.csv`

Columns:
- `report_date`: Report publication date
- `report_week`: Reporting week number
- `pathogen`: Pathogen name
- `ili_percent`: Outpatient ILI positive rate (%)
- `sari_percent`: Inpatient SARI positive rate (%)

**Pathogens monitored:** SARS-CoV-2, Influenza, RSV, Adenovirus, hMPV, PIV, Common Coronaviruses, Bocavirus, Rhinovirus, Enterovirus, Mycoplasma pneumoniae, and others.

## Data Notes

⚠️ **2025 Weeks 14-22:** CDC published monthly reports during this period. Only COVID-19 data was manually updated for these weeks.

## Data Source

Data extracted from official China CDC surveillance reports. Updated weekly on Sundays.

## Contact

- Email: yang_kaixin@gzlab.ac.cn

## Disclaimer

Data provided for academic research and analysis. Please verify data quality before use.
