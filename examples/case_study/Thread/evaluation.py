import yaml
import subprocess
import time
import json
# 检查 JSON 字符串是否包含表示实验已结束的状态
def is_experiment_completed(result_json):
    result_json = json.loads(result_json, strict=False)
    # 将 JSON 字符串解析为 Python 对象（列表）
    try:
        experiments = json.loads(result_json)
    except json.JSONDecodeError:
        print("Invalid JSON format.")
        return False

    # 检查每个实验的状态
    for experiment in experiments:
        status = experiment.get("status", "")
        if status not in ["SUCCEEDED", "FAILED", "STOPPED"]:
            return False  # 如果有任何实验仍在运行，返回 False

    return True  # 所有实验都已结束

# 配置文件路径 nnictl create --config /home/huanting/PROM/examples/case_study/Thread/config.yaml --port 8088
yaml_file = "/home/huanting/PROM/examples/case_study/Thread/config.yaml"

# 要运行的命令列表和对应的端口
experiments = [
    # {"command": "python Thread_i2v.py --mode train", "port": 8088},
    {"command": "python Thread_i2v.py --mode deploy", "port": 8089},
    {"command": "python Thread_Deep.py --mode train", "port": 8090},
    {"command": "python Thread_Deep.py --mode deploy", "port": 8091},
    {"command": "python Thread_magni.py --mode train", "port": 8092},
    {"command": "python Thread_magni.py --mode deploy", "port": 8093},
]
subprocess.run(["nnictl", "stop", "-a"], capture_output=True, text=True)

for exp in experiments:
    # 加载现有的 YAML 文件
    with open(yaml_file, 'r') as file:
        config = yaml.safe_load(file)

    # 修改 command 和 port
    config['trial']['command'] = exp['command']

    # 保存修改后的 YAML 文件
    with open(yaml_file, 'w') as file:
        yaml.dump(config, file)

    # 运行 NNI 实验
    subprocess.Popen(["nnictl", "create", "--config", yaml_file, "--port", str(exp['port'])])



    print(f"Waiting for experiment to complete...")
    time.sleep(1*60*60)

# subprocess.run(["nnictl", "stop", "-a"], capture_output=True, text=True)
