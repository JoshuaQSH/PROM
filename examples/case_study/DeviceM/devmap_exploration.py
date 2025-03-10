import numpy as np
import nni
from sklearn.model_selection import StratifiedKFold
from compy import datasets as D
from compy import models as M
from compy import representations as R
from compy.representations.extractors import ClangDriver
import random
import warnings
import sys
# sys.path.append('/home/huanting/model/compy-learn-master')
import torch
warnings.filterwarnings('ignore')

# Load dataset
def train(suite_train,suite_test,dataset,combinations,random_seed):
    for builder, visitor, model in combinations:
        print("Processing %s-%s-%s" % (builder.__name__, visitor.__name__, model.__name__))

        # Build representation
        clang_driver = ClangDriver(
            ClangDriver.ProgrammingLanguage.OpenCL,
            ClangDriver.OptimizationLevel.O3,
            [(x, ClangDriver.IncludeDirType.User) for x in dataset.additional_include_dirs],
            ["-xcl", "-target", "x86_64-pc-linux-gnu"],
        )
        data_train = dataset.preprocess(builder(clang_driver), visitor,suite_train)
        data_test = dataset.preprocess(builder(clang_driver), visitor, suite_test)

        # Train and test
        kf = StratifiedKFold(n_splits=3, shuffle=True, random_state=random_seed) #
        split = kf.split(data_train["samples"], [sample["info"][5] for sample in data_train["samples"]])


        if data_train["num_types"] > data_test["num_types"]:
            num_types = data_train["num_types"]
        else:
            num_types =data_test["num_types"]

        test_idx = np.arange(len(data_test["samples"]))

        for train_idx, val_idx in split:
            model_train = model(num_types=num_types)
            il_speed_up,best_speedup,model_path,percent_mean = model_train.train(
                list(np.array(data_train["samples"])[train_idx]),
                list(np.array(data_train["samples"])[val_idx]),
                list(np.array(data_test["samples"])[test_idx]),
                random_seed
            )
            best_speedup=np.max(il_speed_up)
            break

        # print("best improved speed up is : ", best_speedup)

        nni.report_final_result(percent_mean)

def load_pickle( suite_train, suite_test, dataset,combinations,random_seed,model_path):
    global val_idx

    for builder, visitor, model in combinations:
        print("Processing %s-%s-%s" % (builder.__name__, visitor.__name__, model.__name__))
        # Build representation
        clang_driver = ClangDriver(
            ClangDriver.ProgrammingLanguage.OpenCL,
            ClangDriver.OptimizationLevel.O3,
            [(x, ClangDriver.IncludeDirType.User) for x in dataset.additional_include_dirs],
            ["-xcl", "-target", "x86_64-pc-linux-gnu"],
        )
        data_train = dataset.preprocess(builder(clang_driver), visitor, suite_train)
        data_test = dataset.preprocess(builder(clang_driver), visitor, suite_test)

        # Train and test

        kf = StratifiedKFold(n_splits=3, shuffle=True, random_state=random_seed)  #
        split = kf.split(data_train["samples"], [sample["info"][5] for sample in data_train["samples"]])

        for train_idx, val_idx in split:
            print(val_idx)
            val_idx=val_idx
            break

        if data_train["num_types"]>data_test["num_types"]:
            num_types = data_train["num_types"]
        else:
            num_types = data_test["num_types"]
        # valid
        model_valid = model(num_types=num_types, mode='test', model_path=model_path)
        valid_acc, speed_up, valid_batches = model_valid.valid(
            list(np.array(data_train["samples"])[val_idx]))
        # print("valid_accuracy:"" %.4f" % (valid_acc))
        # print("valid_speed_up:"" %.4f" % (speed_up))

        #test
        test_idx = np.arange(len(data_test["samples"]))
        model_test = model(num_types=num_types, mode='test', model_path=model_path)
        test_acc, speed_up, test_batches = \
            model_test.test(list(np.array(data_test["samples"])[test_idx])
                            , valid_batches, mode_uq='reca')

        print("test_accuracy:"" %.4f" % (test_acc))
        print("test_speed_up:"" %.4f" % (speed_up))

        # uq
        model_uq = model(num_types=num_types, mode='test', model_path=model_path)
        uq_acc,uq_speed_up,test_batches = \
            model_uq.uq(list(np.array(data_test["samples"])[test_idx]),valid_batches,mode_uq='reca')


        print("uq_accuracy:"" %.4f" % (uq_acc))
        print("uq_speed_up:"" %.4f"% (uq_speed_up))

if __name__ == '__main__':
    random_seed = random.randint(0, 9999)
    # random_seed=3407
    torch.manual_seed(random_seed)
    dataset = D.OpenCLDevmapDataset()
    # Explore combinations
    combinations = [
        # CGO 20: AST+DF, CDFG
        # (R.ASTGraphBuilder, R.ASTDataVisitor, M.GnnPytorchGeomModel),
        #meiyongdao (R.LLVMGraphBuilder, R.LLVMCDFGVisitor, M.GnnPytorchGeomModel),
        # Arxiv 20: ProGraML
        # (R.LLVMGraphBuilder, R.LLVMProGraMLVisitor, M.GnnPytorchGeomModel),
        # PACT 17: DeepTune
        # (R.SyntaxSeqBuilder, R.SyntaxTokenkindVariableVisitor, M.RnnTfModel),
        # Extra
        # (R.ASTGraphBuilder, R.ASTDataCFGVisitor, M.GnnPytorchGeomModel),
        # (R.LLVMGraphBuilder, R.LLVMCDFGCallVisitor, M.GnnPytorchGeomModel),
        (R.LLVMGraphBuilder, R.LLVMCDFGPlusVisitor, M.GnnPytorchGeomModel),
    ]
    suite = {
        "amd-app-sdk-3.0": {"subdir": "samples/opencl/cl/1.x"}, #16
        # "npb-3.3": {"subdir": ""}, #527
        "nvidia-4.2": {"subdir": "OpenCL/src", "benchmark_name_prefix": "ocl"}, #12
        "parboil-0.2": {"subdir": "benchmarks"}, #19
        "polybench-gpu-1.0": {
            "subdir": "OpenCL",
            "remappings": {
                "2DConvolution": "2DCONV",
                "2mm": "2MM",
                "3DConvolution": "3DCONV",
                "3mm": "3MM",
                "atax": "ATAX",
                "bicg": "BICG",
                "correlation": "CORR",
                "covariance": "COVAR",
                "gemm": "GEMM",
                "gesummv": "GESUMMV",
                "gramschmidt": "GRAMSCHM",
                "mvt": "MVT",
                "syr2k": "SYR2K",
                "syrk": "SYRK",
            },
        }, #27
        # "rodinia-3.1": {"subdir": "opencl", }, #28
        # "shoc-1.1.5": {"subdir": "src/opencl/level1"}, #48
    }
    # suite_test = {
    #     "nvidia-4.2": {"subdir": "OpenCL/src", "benchmark_name_prefix": "ocl"},
    #     "npb-3.3": {"subdir": ""},
    #     "shoc-1.1.5": {"subdir": "src/opencl/level1"},
    #     "rodinia-3.1": {"subdir": "opencl", },
    #     "parboil-0.2": {"subdir": "benchmarks"},
    # }
    # import random

    def split_dict(dct, test_ratio=0.5,random_seed=0):
        """
        从字典中随机划分训练集和测试集
        :param dct: 字典
        :param test_ratio: 测试集占比，默认为0.2
        :return: 训练集和测试集组成的元组
        """
        # dict_add={"npb-3.3": {"subdir": ""}}
        keys = list(dct.keys())
        random.seed(random_seed)
        random.shuffle(keys)  # 随机打乱键的顺序
        n_test = int(len(keys) * test_ratio)  # 计算测试集大小
        test_keys = keys[:n_test]  # 获取测试集的键
        train_keys = keys[n_test:] # 获取训练集的键
        test_dict = {key: dct[key] for key in test_keys}  # 构建测试集字典
        train_dict = {key: dct[key] for key in train_keys}  # 构建训练集字典
        # train_dict.update(dict_add)
        return train_dict, test_dict

    print("random_seed",random_seed)
    suite_train, suite_test = split_dict(suite,0.3,random_seed)
    print("suite_train", suite_train)
    print("test_dict", suite_test)

    # train(suite_train,suite_test,dataset,combinations,random_seed)
    print("random_seed: ", random_seed)

    # nni

    model_path=\
        r'/home/huanting/PROM/examples/case_study/DeviceM/compy/save_model/8489_0.7580507466493636.pkl'
    load_pickle(suite_train, suite_test, dataset,combinations,
                random_seed,
                model_path)
    # nnictl create --config /home/huanting/model/compy-learn-master/config.yml --port 8088
