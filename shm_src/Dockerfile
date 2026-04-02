FROM public.ecr.aws/lambda/python:3.11

RUN yum install -y gcc gcc-c++ make
RUN pip install --upgrade pip

# NumPy 1.x 대의 안정 버전 설치
# --only-binary 옵션은 컴파일을 시도하지 말고 빌드된 파일을 가져오라는 뜻
RUN pip install --no-cache-dir "numpy<2"
RUN pip install --no-cache-dir "pyarrow<16" --only-binary :all:

WORKDIR ${LAMBDA_TASK_ROOT}

# 파일 복사
COPY handler.py shm_registry.py shm_init.py ${LAMBDA_TASK_ROOT}/

# 실행 핸들러 설정 (형식: 파일명.함수명)
CMD ["handler.hello_handler"]
