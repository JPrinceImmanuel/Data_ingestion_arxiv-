from google.cloud import storage
import os
from google.oauth2 import service_account
import random
from datetime import datetime, timedelta
import arxiv
import tempfile
import requests 
from dotenv import load_dotenv
#from arxiv-mcp-server import server


load_dotenv()
# GCP credentials will be automatically detected from GOOGLE_APPLICATION_CREDENTIALS env var
gcp_project_id = os.getenv("GCP_PROJECT_ID")
credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
redentials = service_account.Credentials.from_service_account_file(credentials_path)


def upload_file(file_name, bucket, object_name=None):
    """Upload a file to a GCP Cloud Storage bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: GCS object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """
    if object_name is None:
        object_name = os.path.basename(file_name)

    storage_client = storage.Client(credentials=credentials, project=gcp_project_id)
    bucket_obj = storage_client.bucket(bucket)
    blob = bucket_obj.blob(object_name)
    try:
        blob.upload_from_filename(file_name)
        return True
    except Exception as e:
        print(f"Error uploading file to GCS: {e}")
        return False


def get_window(days_back=10, window_size=24):
    now = datetime.now()
    rand = random.randint(0, days_back * 24)

    start = now - timedelta(hours=rand + window_size)
    end = now - timedelta(hours=rand)
    print(start, end, rand)
    return start, end


def ingestion(query, bucket_name):
    start, end = get_window()
    search = arxiv.Search(
        query=f"{query} AND submittedDate:[{start.strftime('%Y%m%d')} TO {end.strftime('%Y%m%d')}]",
        max_results=100,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )
    storage_client = storage.Client()
    bucket_obj = storage_client.bucket(bucket_name)

    for paper in search.results():
        paper_id = paper.entry_id.split("/")[-1]
        gcs_key = f"raw/{paper_id}.pdf"

        # Download the PDF
        pdf_url = paper.pdf_url
        try:
            response = requests.get(pdf_url)
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(response.content)
                tmp.flush()
                # Upload to GCS with metadata
                blob = bucket_obj.blob(gcs_key)
                blob.metadata = {
                    "title": paper.title[:512],
                    "published": str(paper.published),
                    "paper_id": paper_id
                }
                blob.upload_from_filename(tmp.name)
        except Exception as e:
            print(f"Error processing paper {paper_id}: {e}")


# Example usage
query = "Retrieval-Augmented Generation OR RAG"
ingestion(query, "arxivpaperspan")