cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/scripts"

bash deploy_base_lambda.sh
bash deploy_shm_lambda.sh

bash call_base_func.sh
bash call_shm_func.sh
