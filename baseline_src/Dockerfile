FROM public.ecr.aws/lambda/python:3.9

WORKDIR ${LAMBDA_TASK_ROOT}

COPY integerated_handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.hello_handler"]
