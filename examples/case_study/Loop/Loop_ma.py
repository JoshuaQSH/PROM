import sys
import os
import warnings

# from sklearn.metrics import accuracy_score

warnings.filterwarnings("ignore")
import random
sys.path.append('./case_study/Loop')
sys.path.append('/cgo/prom/PROM/src')
sys.path.append('/cgo/prom/PROM/thirdpackage')

from Magni_utils import Magni,LoopT,make_prediction,make_prediction_il


import numpy as np
import nni
import argparse
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.svm import SVC
from src.prom.prom_util import Prom_utils

def load_deeptune_args():
    """
        Load arguments for DeepTune model training and deployment.

        Retrieves hyperparameters from the tuner or sets default values if none are provided.
        These arguments include settings like the random seed, epoch count, and batch size.

        Returns
        -------
        argparse.Namespace
            Parsed command-line arguments with parameters such as seed, mode, epoch, and batch size.
    """
    # get parameters from tuner
    params = nni.get_next_parameter()
    if params == {}:
        params = {
            "epoch": 5, # 5,10,15,20
            "batch_size": 64, # 32,64,128
            "seed": 9408,
        }

    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=params['seed'],
                        help="random seed for initialization")
    parser.add_argument('--epoch', type=int, default=params['epoch'],
                        help="random seed for initialization")
    parser.add_argument("--batch_size", default=params['batch_size'], type=int,
                        help="Batch size per GPU/CPU for training.")
    parser.add_argument('--mode', choices=['train', 'deploy'], help="Mode to run: train or deploy")
    args = parser.parse_args()
    args.seed=int(args.seed)
    print("seeds is", args.seed)
    # train the underlying model
    # deeptune_model = DeepTune()
    # deeptune_model.init(args)
    return args

def loop_main(tasks="deeptune"):
    """
    Main function to train and deploy DeepTune model for loop performance optimization.

    Loads and partitions the dataset, trains the model, saves the trained model, and
    evaluates performance using conformal prediction with incremental learning.

    Parameters
    ----------
    tasks : str, optional
        Specifies the task mode; defaults to 'deeptune'.
    """
    prom_loop = LoopT(model=DeepTune())
    deeptune_model = DeepTune()


    args = load_deeptune_args()
    origin_speedup_all = []
    speed_up_all = []
    improved_spp_all = []
    deeptune_model.init(args)

    # Load dataset
    # print(f"*****************{platform}***********************")
    print(f"Loading dataset")
    X_seq, y_1hot,time,train_index, valid_index, test_index = \
        prom_loop.data_partitioning(dataset=r'../../../benchmark/Loop/data_dict.pkl', calibration_ratio=0.1, args=args)
    train_index=train_index[:100]
    valid_index=valid_index[:100]
    test_index=test_index[:100]
    #  init the model
    print(f"Loading underlying model...")
    prom_loop.model.init(args)
    seed_value = int(args.seed)
    prom_loop.model.train(
        sequences=X_seq[train_index], verbose=False, y_1hot=y_1hot[train_index]
    )
    # save the model
    model_path = f"models/loop/{seed_value}.model"
    try:
        os.mkdir(os.save.dirname(model_path))
    except:
        pass
    prom_loop.model.save(model_path)

    # load the model
    # prom_loop.model.restore(r'/cgo/prom/PROM/examples/case_study/Loop/models/loop/123.model')
    # make prediction
    origin_speedup, all_pre = deeptune_make_prediction\
        (model=deeptune_model, X_seq=X_seq, y_1hot=y_1hot,
         time=time, test_index=test_index)
    print(f"Loading successful, the speedup is {origin_speedup:.2%}")
    # origin = sum(speed_up_all) / len(speed_up_all)
    # print("final percent:", origin)
    # nni.report_final_result(origin)

    # Conformal Prediction
    # the underlying model
    print(f"Start conformal prediction...")
    clf = prom_loop.model
    # the prom parameters
    method_params = {
        "lac": ("score", True),
        "top_k": ("top_k", True),
        "aps": ("cumulated_score", True),
        "raps": ("raps", True)
    }
    # the prom object
    Prom_thread = Prom_utils(clf, method_params, task="loop")
    # conformal prediction

    calibration_data = X_seq[valid_index]
    cal_y= y_1hot[valid_index]
    # cal_y = np.argmax(y_1hot[valid_index], axis=1)

    test_x = X_seq[test_index]
    test_y = y_1hot[test_index]
    y = np.argmax(y_1hot[test_index], axis=1) # the true label with 0/1/2/3/4
    y_preds, y_pss, p_value = Prom_thread.conformal_prediction(
        cal_x=calibration_data, cal_y=cal_y, test_x=test_x, test_y=test_y, significance_level="auto")

    # evaluate conformal prediction
    index_all_right, index_list_right, Acc_all, F1_all, Pre_all, Rec_all \
        = Prom_thread.evaluate_conformal_prediction \
        (y_preds=y_preds, y_pss=y_pss, p_value=p_value, all_pre=all_pre, y=y)

    # Increment learning
    print("Finding the most valuable instances for incremental learning...")
    train_index, test_index = Prom_thread.incremental_learning \
        (args.seed, test_index, train_index)
    # retrain the model
    print("Retraining the model...")

    prom_loop.model.train(
            sequences=X_seq[train_index], verbose=0, y_1hot=y_1hot[train_index]
        )
    # test the pretrained model
    retrained_speedup, inproved_speedup = deeptune_make_prediction_il\
        (model_il=deeptune_model, X_seq=X_seq, y_1hot=y_1hot, time=time,
                       test_index=test_index, origin_speedup=origin_speedup)

    print(
        f"origin speed up: {origin_speedup}, "
        f"Imroved speed up: {retrained_speedup}, "
        f"Imroved mean speed up: {inproved_speedup}, "
    )

def loop_train_magni(args):
    """
    Train the Magni model for loop performance optimization.

    Loads and partitions the dataset, initializes the model, and trains it on the training set.
    It also saves the model's performance metrics and generates performance plots.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command-line arguments containing training parameters like seed and batch size.
    """
    # load args
    prom_loop = LoopT(model=Magni())
    Magni_model = Magni()
    origin_speedup_all = []
    speed_up_all = []
    improved_spp_all = []
    Magni_model.init(args)

    # Load dataset
    # print(f"*****************{platform}***********************")
    print(f"Loading dataset")
    X_seq, y_1hot, time, train_index, valid_index, test_index = \
        prom_loop.data_partitioning(dataset=r'../../../benchmark/Loop/data_dict.pkl', calibration_ratio=0.1,
                                    args=args)
    train_index = train_index[:1000]
    valid_index = valid_index[:400]
    test_index = test_index[:200]
    # train_index = train_index[:100]
    # valid_index = valid_index[:100]
    # test_index = test_index[:100]
    #  init the model
    print(f"Loading underlying model...")
    prom_loop.model.init(args)
    seed_value = int(args.seed)
    prom_loop.model.train(
        cascading_features=X_seq[train_index],
        cascading_y=y_1hot[train_index],
        verbose=True,
    )

    # save the model
    # model_dir_path = "logs/train/models/ma/"
    plot_figure_path = 'logs/train/figs/ma/plot'
    plot_figuredata_path = 'logs/train/figs/ma/data'
    # os.makedirs(os.path.dirname(model_dir_path), exist_ok=True)
    os.makedirs(os.path.dirname(plot_figure_path), exist_ok=True)
    os.makedirs(os.path.dirname(plot_figuredata_path), exist_ok=True)
    # model_path = f"logs/train/models/ma/magni_{seed_value}.model"
    # prom_loop.model.save(model_path)

    # load the model
    # prom_loop.model.restore(r'/cgo/prom/PROM/examples/case_study/Loop/models/loop/123.model')
    # make prediction
    origin_speedup, all_pre, data_distri = make_prediction \
        (model=prom_loop.model, X_feature=X_seq, y_1hot=y_1hot,
         time=time, test_index=test_index)
    print(f"Loading successful, the speedup is {origin_speedup}")

    ######
    import matplotlib.pyplot as plt
    import seaborn as sns
    import pandas as pd
    plt.boxplot(data_distri)
    data_df = pd.DataFrame({'Data': data_distri})
    sns.violinplot(data=data_df, y='Data')
    seed_save = str(int(seed_value))
    plt.title('Box Plot Example ' + seed_save)
    plt.ylabel('Values')

    plt.savefig(plot_figure_path + str(origin_speedup) + '_' + str(
        seed_save) + '.png')
    data_df.to_pickle(
        plot_figuredata_path + str(origin_speedup) + '_' + str(
            seed_save) + '_data.pkl')
    # plt.show()
    print("training finished")
    nni.report_final_result(origin_speedup)

def loop_deploy_magni(args):
    """
    Deploy and evaluate the Magni model for loop performance optimization.

    Initializes the model, loads the dataset, and partitions it for evaluation.
    The function also performs conformal prediction, evaluates performance metrics,
    and applies incremental learning to improve model performance.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command-line arguments containing deployment parameters like seed and batch size.
    """

    # load args
    prom_loop = LoopT(model=Magni())
    Magni_model = Magni()
    origin_speedup_all = []
    speed_up_all = []
    improved_spp_all = []
    Magni_model.init(args)

    # Load dataset
    # print(f"*****************{platform}***********************")
    print(f"Loading dataset")
    X_seq, y_1hot, time, train_index, valid_index, test_index = \
        prom_loop.data_partitioning(dataset=r'../../../benchmark/Loop/data_dict.pkl', calibration_ratio=0.1,
                                    args=args)
    train_index = train_index[:1000]
    valid_index = valid_index[:400]
    test_index = test_index[:200]
    # train_index = train_index[:100]
    # valid_index = valid_index[:100]
    # test_index = test_index[:100]
    #  init the model
    print(f"Loading underlying model...")
    prom_loop.model.init(args)
    seed_value = int(args.seed)
    prom_loop.model.train(
        cascading_features=X_seq[train_index],
        cascading_y=y_1hot[train_index],
        verbose=True,
    )

    # save the model
    # model_dir_path = "logs/train/models/ma/"
    plot_figure_path = 'logs/train/figs/ma/plot'
    plot_figuredata_path = 'logs/train/figs/ma/data'
    # os.makedirs(os.path.dirname(model_dir_path), exist_ok=True)
    os.makedirs(os.path.dirname(plot_figure_path), exist_ok=True)
    os.makedirs(os.path.dirname(plot_figuredata_path), exist_ok=True)
    # model_path = f"logs/train/models/ma/magni_{seed_value}.model"
    # prom_loop.model.save(model_path)

    # load the model
    # prom_loop.model.restore(r'/cgo/prom/PROM/examples/case_study/Loop/models/loop/123.model')
    # make prediction
    origin_speedup, all_pre, data_distri = make_prediction \
        (model=prom_loop.model, X_feature=X_seq, y_1hot=y_1hot,
         time=time, test_index=test_index)
    print(f"Loading successful, the speedup is {origin_speedup}")

    ######
    import matplotlib.pyplot as plt
    import seaborn as sns
    import pandas as pd
    plt.boxplot(data_distri)
    data_df = pd.DataFrame({'Data': data_distri})
    sns.violinplot(data=data_df, y='Data')
    seed_save = str(int(seed_value))
    plt.title('Box Plot Example ' + seed_save)
    plt.ylabel('Values')

    plt.savefig(plot_figure_path + str(origin_speedup) + '_' + str(
        seed_save) + '.png')
    data_df.to_pickle(
        plot_figuredata_path + str(origin_speedup) + '_' + str(
            seed_save) + '_data.pkl')
    # plt.show()
    print("training finished")
    # print("final percent:", origin)
    # nni.report_final_result(origin)

    # Conformal Prediction
    # the underlying model
    print(f"Start conformal prediction...")
    clf = prom_loop.model
    # the prom parameters
    method_params = {
        "lac": ("score", True),
        "top_k": ("top_k", True),
        "aps": ("cumulated_score", True),
        "raps": ("raps", True)
    }
    # the prom object
    Prom_thread = Prom_utils(clf, method_params, task="loop")
    # conformal prediction

    calibration_data = X_seq[valid_index]
    cal_y = y_1hot[valid_index]
    # cal_y = np.argmax(y_1hot[valid_index], axis=1)

    test_x = X_seq[test_index]
    test_y = y_1hot[test_index]
    y = np.argmax(y_1hot[test_index], axis=1)  # the true label with 0/1/2/3/4
    y_preds, y_pss, p_value = Prom_thread.conformal_prediction(
        cal_x=calibration_data, cal_y=cal_y, test_x=test_x, test_y=test_y, significance_level="auto")

    # evaluate conformal prediction
    # MAPIE
    Prom_thread.evaluate_mapie \
        (y_preds=y_preds, y_pss=y_pss, p_value=p_value, all_pre=all_pre, y=y,
         significance_level=0.05)

    Prom_thread.evaluate_rise \
        (y_preds=y_preds, y_pss=y_pss, p_value=p_value, all_pre=all_pre, y=y,
         significance_level=0.05)

    index_all_right, index_list_right, Acc_all, F1_all, Pre_all, Rec_all,_,_ \
        = Prom_thread.evaluate_conformal_prediction \
        (y_preds=y_preds, y_pss=y_pss, p_value=p_value, all_pre=all_pre, y=y,significance_level='auto')

    # Increment learning
    print("Finding the most valuable instances for incremental learning...")
    train_index, test_index = Prom_thread.incremental_learning \
        (args.seed, test_index, train_index)
    # retrain the model
    print("Retraining the model...")
    prom_loop.model.train(
        cascading_features=X_seq[train_index],
        cascading_y=y_1hot[train_index],
        verbose=0,
    )

    # test the pretrained model
    retrained_speedup, inproved_speedup = make_prediction_il \
        (model_il=prom_loop.model, X_feature=X_seq, y_1hot=y_1hot, time=time,
         test_index=test_index, origin_speedup=origin_speedup)
    print(
        f"origin speed up: {origin_speedup}, "
        f"Imroved speed up: {retrained_speedup}, "
        f"Imroved mean speed up: {inproved_speedup}, "
    )

    nni.report_final_result(inproved_speedup)


if __name__=='__main__':
    args = load_deeptune_args()
    if args.mode == 'train':
        loop_train_magni(args=args)
    elif args.mode == 'deploy':
        loop_deploy_magni(args=args)
    # loop_train_magni(args)
    loop_deploy_magni(args)
    # nnictl create --config /cgo/prom/PROM/examples/case_study/Loop/config.yaml --port 8088
