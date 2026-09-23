# ============================================================================
#  Dockerfile for THIS directory's service: the INGESTION WORKER.
#  Runs on AWS Lambda.
#
#  It sits next to the code it builds -- app/ingestion/indexer.py is right
#  here, and lambda_handler at the bottom of that file is the entrypoint.
#
#  Build from the REPO ROOT, because the image needs app/ and
#  requirements.txt, and Docker can only copy from inside the build context:
#
#      docker build -f app/ingestion/Dockerfile -t rag-ingest .
#                      ^ the recipe                  ^ the context (repo root)
#
#  Starts:  app/ingestion/indexer.py -> lambda_handler
#
#  Note what is NOT here: no port, no EXPOSE, no uvicorn, no appuser. Lambda
#  supplies all of that. The base image below already has the Lambda runtime
#  client as its ENTRYPOINT, which is why CMD is just the name of a Python
#  function.
# ============================================================================

FROM public.ecr.aws/lambda/python:3.12

# LAMBDA_TASK_ROOT is /var/task, where Lambda looks for your code.
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY app/ ${LAMBDA_TASK_ROOT}/app/

# module.path.to.function -- Lambda calls this on every invocation.
CMD ["app.ingestion.indexer.lambda_handler"]
