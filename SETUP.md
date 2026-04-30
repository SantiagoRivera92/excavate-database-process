# Quick Setup Guide

## What was created

A standalone GitHub Actions workflow in the `github/` folder that contains everything needed to run data_ingestion independently.

## Files structure

```
github/
├── .github/workflows/data_ingestion.yml  # GitHub Actions workflow
├── data/                                  # Data files (formats, inputs, outputs)
├── data_ingestion.py                      # Main script (modified)
├── mediawiki_api.py                       # Yugipedia API helper
├── meta_dump.py                           # Meta data dump script
├── requirements.txt                       # Python dependencies
├── .gitignore                            # Git ignore rules
└── README.md                             # Documentation
```

## Changes made

1. **Removed `load_dotenv.py` dependency** - Now uses environment variables directly
2. **Simplified MongoDB connection** - Uses single `MONGO_URI` instead of separate dev/prod URIs
3. **Created necessary directories** - Ensures `data/input/` and `mediawiki_cache/` exist
4. **Added GitHub Actions workflow** - Runs daily at midnight, supports manual trigger

## Required GitHub Secrets

Add these secrets in your repository settings (Settings → Secrets and variables → Actions):

- `MONGO_URI` - Your MongoDB connection string
- `S3_API_URL` - S3/Cloudflare R2 API URL  
- `S3_BUCKET_NAME` - S3 bucket name
- `S3_ACCESS_KEY` - S3 access key
- `S3_SECRET_KEY` - S3 secret key

## Usage

The workflow will run automatically daily. To trigger manually:
1. Go to the Actions tab in your GitHub repository
2. Select "Data Ingestion" workflow
3. Click "Run workflow"

## Testing locally

```bash
cd github/
export MONGO_URI="your_mongo_uri"
export S3_API_URL="your_s3_api_url"
export S3_BUCKET_NAME="your_bucket_name"
export S3_ACCESS_KEY="your_access_key"
export S3_SECRET_KEY="your_secret_key"
pip install -r requirements.txt
python data_ingestion.py
```
