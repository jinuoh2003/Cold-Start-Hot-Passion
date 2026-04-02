FROM public.ecr.aws/lambda/python:3.11

# 1. 빌드 도구 설치 (필요하긴 하지만, 여기서는 바이너리 설치를 우선함)
RUN yum install -y gcc gcc-c++ make

# 2. pip 업데이트 및 pyarrow 설치 (버전 고정 및 바이너리 우선 사용)
RUN pip install --upgrade pip

# NumPy 2.x를 피하기 위해 1.x 대의 마지막 안정 버전을 먼저 설치하고 pyarrow를 설치합니다.
# --only-binary 옵션은 컴파일을 시도하지 말고 빌드된 파일을 가져오라는 뜻입니다.
RUN pip install --no-cache-dir "numpy<2"
RUN pip install --no-cache-dir "pyarrow<16" --only-binary :all:

WORKDIR ${LAMBDA_TASK_ROOT}

# 3. 파일 복사 (파일명 확인: handler.py로 복사하거나 CMD를 수정해야 함)
# 아까 보여주신 파일명이 handler.py였으므로 이름을 맞춰줍니다.
COPY integrated_handler1.py ringbuffer.py shm_init.py ${LAMBDA_TASK_ROOT}/

# 4. 실행 핸들러 설정 (파일명.함수명)
# 파일명이 handler.py 이고 함수가 hello_handler 이므로 아래가 정답입니다.
CMD ["integrated_handler1.hello_handler"]
