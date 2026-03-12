import boto3
import os
import random 
from datetime import datetime, timedelta
import arxiv
import tempfile

os.environ["AWS_ACCESS_KEY_ID"] = 
os.environ["AWS_SECRET_ACCESS_KEY"] = 


  
def upload_file(file_name, bucket, object_name=None):
    """Upload a file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = os.path.basename(file_name)

    # Upload the file
    s3_client = boto3.client('s3')
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True
  
  
def get_window(days_back = 10, window_size = 24):
  now = datetime.now()
  rand = random.randint(0,days_back * 24)
  
  start = now - timedelta(hours= rand + window_size) 
  end = now - timedelta(hours = rand)
  print(start, end, rand)
  return start, end


def ingestion(query):
  start , end = get_window()
  client = arxiv.Client()
  search = arxiv.Search(
    query = f"{query} AND submittedDate:[{start.strftime('%Y%m%d')} TO {end.strftime('%Y%m%d')}]",
    max_results=100,
    sort_by = arxiv.SortCriterion.SubmittedDate
  )
  s3 = boto3.client('s3')
  results = client.results(search)
  for i in results:
    print(i.entry_id)
  
  for paper in client.results(search):
        paper_id = paper.entry_id.split("/")[-1]
        s3_key = f"raw/{paper_id}.pdf"

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            paper.download_pdf(filename=tmp.name)
            s3.upload_file(
                tmp.name, "arxivpaperspa", s3_key,
                ExtraArgs={"Metadata": {
                    "title": paper.title[:512],
                    #"authors": ", ".join(a.name for a in paper.authors)[:512],
                    "published": str(paper.published),
                    "paper_id": paper_id
                }}
            )

  
ingestion("rag")