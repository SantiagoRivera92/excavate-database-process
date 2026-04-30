# Data Ingestion GitHub Action

This is a standalone GitHub Action for running the data ingestion script.

## Setup

1. Fork or copy this folder to your repository
2. Add the following secrets to your GitHub repository settings:

### Required Secrets

- `MONGO_URI`: Your MongoDB connection string
- `S3_API_URL`: S3/Cloudflare R2 API URL
- `S3_BUCKET_NAME`: S3 bucket name
- `S3_ACCESS_KEY`: S3 access key
- `S3_SECRET_KEY`: S3 secret key

### Optional Configuration

The workflow runs daily at midnight. You can also trigger it manually from the Actions tab.

## File Structure

```
github/
├── .github/
│   └── workflows/
│       └── data_ingestion.yml
├── data/
│   ├── input/
│   ├── output/
│   ├── formats/
│   └── formats_md/
├── data_ingestion.py
├── mediawiki_api.py
├── meta_dump.py
└── requirements.txt
```

## Manual Testing

To test locally:

```bash
export MONGO_URI="your_mongo_uri"
export S3_API_URL="your_s3_api_url"
export S3_BUCKET_NAME="your_bucket_name"
export S3_ACCESS_KEY="your_access_key"
export S3_SECRET_KEY="your_secret_key"

pip install -r requirements.txt
python data_ingestion.py
```
