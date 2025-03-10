import os
import random
# import matplotlib.pyplot as plt
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import GaussianNB
import sys
sys.path.append('/home/huanting/PROM/thirdpackage')
from prom.prom_classification import MapieClassifier
from prom.metrics import (classification_coverage_score,
                           classification_mean_width_score)
import math
from sklearn.metrics import f1_score, accuracy_score, precision_score, recall_score
from sklearn.metrics import classification_report

class ModelDefinition:
    """
    Defines a machine learning model with methods for data partitioning, prediction, and feature extraction.
    """
    def __init__(self):
        self.model = None
        self.calibration_data = None
        self.dataset = None

    def data_partitioning(self, dataset, calibration_ratio=0.1):
        """
        Partitions the dataset into training and calibration sets.

        Parameters
        ----------
        dataset : str
            Path to the dataset directory.

        calibration_ratio : float, optional
            Proportion of data used for calibration (default is 0.1).

        Returns
        -------
        tuple
            Tuple containing training and calibration datasets.
        """
        # List all files in the folder
        all_files = [os.path.join(dataset, f) for f in os.listdir(dataset) if
                     os.path.isfile(os.path.join(dataset, f))]

        # Shuffle the files to ensure randomness
        random.shuffle(all_files)

        # Calculate the number of calibration samples
        num_calibration = int(len(all_files) * calibration_ratio)

        # Split the data into calibration and training sets
        calibration_data = all_files[:num_calibration]
        training_data = all_files[num_calibration:]

        return training_data, calibration_data

    def predict(self, X, significant_level=0.1):
        """
        Predicts classes and probabilities using the model.

        Parameters
        ----------
        X : array-like
            Input features for prediction.

        significant_level : float, optional
            Confidence level for predictions (default is 0.1).

        Returns
        -------
        tuple
            Predicted labels and probabilities.
        """
        if self.model is None:
            raise ValueError("Model is not initialized.")
        pred = self.model.predict(X)
        probability = self.model.predict_proba(X)

        return pred,probability

    def feature_extraction(self, input):
        """
        Extracts features from input data using the model.

        Parameters
        ----------
        input : array-like
            Input data for feature extraction.

        Returns
        -------
        array
            Extracted features.
        """
        if self.model is None:
            raise ValueError("Model is not initialized.")

        return self.model.feature_extraction(input)



class Prom_utils:
    """
    Provides utilities for performing conformal prediction and evaluation of classification models.
    """
    def __init__(self,clf,method_params,task):
        """
        Initializes the utility class with a classifier, method parameters, and task-specific settings.

        Parameters
        ----------
        clf : object
            Classifier model.

        method_params : dict
            Parameters for each conformal prediction method.

        task : str
            Task type defining the number of classes.
        """
        self.clf = clf
        self.method_params = method_params
        self.task = task
        if self.task== "thread":
            self.cfs = [1, 2, 4, 8, 16, 32]
        if self.task== "loop":
            self.cfs = list(range(35))
        if self.task== "bug":
            self.cfs = list(range(8))
        if self.task== "dev":
            self.cfs = list(range(2))

    def find_alpha_range(self,n):
        """
        Calculate the minimum and maximum alpha values for a given dataset size.

        Parameters:
        n (int): The number of samples in the dataset.

        Returns:
        tuple: A tuple containing the minimum and maximum alpha values.
        """
        # Calculate initial alpha_min and alpha_max values with added 0.1

        alpha_min=math.floor((max(1 / n, 0) + 0.1) * 10) / 10
        alpha_max = min(1 - 1 / n, 1) + 0.1

        # Round alpha_min and alpha_max up to the nearest tenth and ensure they do not exceed 1
        alpha_min = min(math.ceil(alpha_min * 10) / 10.0, 1/n + 0.02)
        alpha_max = min(math.ceil(alpha_max * 10) / 10.0, 1-1/n - 0.02)

        return alpha_min, alpha_max

    def conformal_prediction(self, cal_x, cal_y, test_x,test_y,significance_level="auto"):
        """
        Perform conformal prediction using various methods.

        Parameters:
        clf (object): The classifier model.
        method_params (dict): Dictionary of method parameters.
        cal_y (array): Calibration data labels.
        test_x (array): Test data features.

        Returns:
        dict: A dictionary containing y_preds, y_pss, and p_value for each method.
        """
        y_preds, y_pss, p_value = {}, {}, {}
        alpha_min, alpha_max = self.find_alpha_range(len(cal_y))
        if significance_level=="auto":
            if alpha_max==alpha_min:
                self.alphas = [alpha_min]
            else:
                self.alphas = np.arange(alpha_min, alpha_max, 0.02)
        else :
            self.alphas = [significance_level]
        try:
            y_cal = np.argmax(cal_y, axis=1)
            self.y_test = np.argmax(test_y, axis=1)
        except:
            y_cal = cal_y
            self.y_test = test_y
        try:
            y_cal = [self.cfs[x] for x in y_cal]
        except:
            pass

        for name, (method, include_last_label) in self.method_params.items():
            mapie = MapieClassifier(estimator=self.clf, method=method, cv="prefit", classes=self.cfs)
            mapie.fit(cal_x, y_cal, task=self.task)
            mapie.prom_test_ncm(test_x, task="thread")
            y_preds[name], y_pss[name], p_value[name] = mapie.predict(cal_x, test_x, alpha=self.alphas,
                                                                      include_last_label=include_last_label)

        return y_preds, y_pss, p_value

    def count_null_set(self,y_ps):
        """
        Counts null sets in prediction results.

        Parameters
        ----------
        y_ps : array-like
            Prediction sets.

        Returns
        -------
        int
            Number of null sets.
        """
        return np.sum(y_ps == 0)

    def classification_coverage_score(self,y_true, y_pred):
        """
        Calculates coverage score for classification predictions.

        Parameters
        ----------
        y_true : array-like
            True labels.

        y_pred : array-like
            Prediction sets.

        Returns
        -------
        float
            Coverage score.
        """
        correct_predictions = 0
        for true, pred_set in zip(y_true, y_pred):
            if true in pred_set:
                correct_predictions += 1
        return correct_predictions / len(y_true)


    def incremental_learning(self,seed_value, test_index, train_index,
                             ):
        """
        Perform Incremental Learning (IL) and evaluate the speedup and accuracy improvements.

        Parameters:
        model (object): The model to be used for prediction and retraining.
        y_test (array): The true labels for the test data.
        y_preds (dict): The predicted labels for the test data.
        name (str): The method name to be used for accuracy evaluation.
        seed_value (int): The seed value for random operations.
        test_index (list): The list of test indices.
        train_index (list): The list of train indices.
        X_seq (array): The sequences used for model training and prediction.
        y_1hot (array): The one-hot encoded labels.
        oracles (dict): The oracle predictions.
        df (DataFrame): The DataFrame containing runtime information.
        platform (str): The platform for which runtime information is considered.
        oracle_runtimes (list): The list of oracle runtimes.

        Returns:
        None
        """

        # origin_accuracy = accuracy_score(y_test, y_preds[name])
        random.seed(seed_value)

        # Select a portion of the test data for retraining
        selected_count = max(int(len(self.y_test) * 0.05), 1)

        try:
            random_element = random.sample(list(self.common_elements), selected_count)
        except:
            random_element = random.sample(range(len(test_index)), selected_count)

        sample = [test_index[index] for index in random_element]

        try:
            train_index += sample
        except:
            train_index = np.concatenate((train_index, sample))
        test_index = [item for item in test_index if item not in sample]

        return train_index, test_index

    def evaluate_conformal_prediction(self, y_preds, y_pss,p_value,all_pre,y, significance_level=0.05):
        """
        Evaluates conformal predictions by calculating accuracy, F1, precision, and recall.

        Parameters
        ----------
        y_preds : dict
            Predicted labels for each method.

        y_pss : dict
            Prediction sets for each method.

        p_value : dict
            P-values for each method.

        all_pre : array-like
            Array of initial predictions.

        y : array-like
            True labels.

        significance_level : float or str, optional
            Significance level for prediction intervals (default is 0.05).

        Returns
        -------
        tuple
            Evaluation results including accuracy, F1, precision, and recall for each method.
        """

        nulls, coverages, accuracies, confidence_sizes, credibility_sizes = {}, {}, {}, {}, {}
        Acc_all = []
        F1_all = []
        Pre_all = []
        Rec_all = []
        credibility_score={}
        if "mixture" in self.method_params:
            del self.method_params["mixture"]
        for name, (method, include_last_label) in self.method_params.items():
            results_array = np.zeros((len(p_value[name]), len(self.alphas)), dtype=bool)
            #step1, use p-value to select
            if significance_level is not "auto":
                self.alphas = [significance_level]
            for i, alpha in enumerate(self.alphas):
                results_array[:, i] = np.array([value > (1 - alpha) for value in p_value[name]])
            credibility_score[name] = results_array


        #step3 vote
        for name, (method, include_last_label) in self.method_params.items():
            accuracies[name] = accuracy_score(self.y_test, y_preds[name])
            nulls[name] = [self.count_null_set(y_pss[name][:, :, i]) for i, _ in enumerate(self.alphas)]
            coverages[name] = [classification_coverage_score(self.y_test, y_pss[name][:, :, i]) for i, _ in
                               enumerate(self.alphas)]
            confidence_sizes[name] = [y_pss[name][:, :, i].sum(axis=1).mean() for i, _ in enumerate(self.alphas)]
            credibility_sizes[name] = [credibility_score[name][i, :].sum().mean() for i, _ in enumerate(self.alphas)]

        if significance_level is "auto":
            # Extract the y_ps at the closest index
            for alpha_num in range(len(self.alphas)):
                # print("The current alpha is: ", self.alphas[alpha_num])
                confidence_result_ps = {method: y_pss[method][:, :, alpha_num] for method in y_pss}
                credibility_result_ps = {method: credibility_score[method][:, alpha_num] for method in
                                         credibility_score}
                # Determine indices for each method
                index_all_tem, index_all_right_tem = {}, {}

                for (method, y_ps1), (_, y_ps2) in zip(credibility_result_ps.items(), confidence_result_ps.items()):
                    for index, confidence_single in enumerate(y_ps2):
                        confidence_true = sum(confidence_single)
                        credibility_true = y_ps1[index]
                        if method not in index_all_tem:
                            index_all_tem[method] = []
                            index_all_right_tem[method] = []
                        if confidence_true == 1 and credibility_true == 1:
                            # elif confidence_true == 1:
                            index_all_right_tem[method].append(index)
                        else:
                            index_all_tem[method].append(index)

                index_all = list(set([idx for indices in index_all_tem.values() for idx in indices]))
                index_list = list(index_all_tem.values())
                index_list.append(index_all)

                index_all_right = list(set(range(len(self.y_test))) - set(index_all))
                index_list_right = list(index_all_right_tem.values())
                index_list_right.append(index_all_right)

                """ compute metircs"""
                # o = y[test_index]
                # correct = p == o
                # 所有错误的
                different_indices = np.where(all_pre != y)[0]
                different_indices_right = np.where(all_pre == y)[0]
                # 找到的错误的： index_list
                # 找的真的错的：num_common_elements
                acc_best = 0
                F1_best = 0
                pre_best = 0
                rec_best = 0
                method_name_best = "NONE"
                self.method_params["mixture"] = ("mixture", False)
                # print("_____________The detection performance can be seen below_____________")
                for index, (single_list, single_list_right) in enumerate(zip(index_list, index_list_right)):
                    self.common_elements = np.intersect1d(single_list, different_indices)
                    num_common_elements = len(self.common_elements)
                    self.common_elements_right = np.intersect1d(single_list_right, different_indices_right)
                    num_common_elements_right = len(self.common_elements_right)
                    try:
                        accuracy = (num_common_elements + num_common_elements_right) / len(all_pre)
                    except:
                        accuracy = 0
                    try:
                        precision = num_common_elements / len(single_list)
                    except:
                        precision = 0
                    try:
                        recall = num_common_elements / len(different_indices)
                    except:
                        recall = 0
                    try:
                        F1 = 2 * precision * recall / (precision + recall)
                    except:
                        F1 = 0

                    # print(
                    #     f"The accuracy for detection on {list(self.method_params.keys())[index]} is: {accuracy * 100:.2f}%, "
                    #     f"precision is: {precision * 100:.2f}%, "
                    #     f"recall is: {recall * 100:.2f}%, "
                    #     f"F1 is: {F1 * 100:.2f}%"
                    # )

                    if F1 > F1_best:
                        method_name_best = list(self.method_params.keys())[index]
                        acc_best = accuracy
                        F1_best = F1
                        pre_best = precision
                        rec_best = recall
                # print(
                #     f"{method_name_best} is the best approach，"
                #     f"the accuracy is: {accuracy * 100:.2f}%, "
                #     f"the precision is: {pre_best * 100:.2f}%, "
                #     f"the recall is: {rec_best * 100:.2f}%, "
                #     f"the F1 is: {F1_best * 100:.2f}%"
                # )
                # print("______________________________________")
                Acc_all.append(acc_best)
                F1_all.append(F1_best)
                Pre_all.append(pre_best)
                Rec_all.append(rec_best)
                # print("The P value is", self.alphas)
                # print("The precision is ", Pre_all)
                # print("The recall is ", Rec_all)
                # print("The F1 is ", F1_all)
                # print("The accuracy is ", Acc_all)

        return index_all_right, index_list_right,Acc_all,F1_all,Pre_all,Rec_all,index_list,self.common_elements,self.alphas

    def evaluate_mapie(self, y_preds, y_pss,p_value,all_pre,y, significance_level=0.05):
        """
        Evaluates conformal predictions using the MAPIE library.

        Parameters
        ----------
        y_preds : dict
            Predicted labels for each method.

        y_pss : dict
            Prediction sets for each method.

        p_value : dict
            P-values for each method.

        all_pre : array-like
            Array of initial predictions.

        y : array-like
            True labels.

        significance_level : float or str, optional
            Significance level for prediction intervals (default is 0.05).

        Returns
        -------
        int
            Status code indicating success.
        """
        nulls, coverages, accuracies, confidence_sizes, credibility_sizes = {}, {}, {}, {}, {}
        Acc_all = []
        F1_all = []
        Pre_all = []
        Rec_all = []
        credibility_score={}
        if "mixture" in self.method_params:
            del self.method_params["mixture"]
        for name, (method, include_last_label) in self.method_params.items():
            results_array = np.zeros((len(p_value[name]), len(self.alphas)), dtype=bool)
            #step1, use p-value to select
            if significance_level is "auto":
                for i, alpha in enumerate(self.alphas):
                    results_array[:, i] = np.array([value > (1 - alpha) for value in p_value[name]])
            else:
                for i, alpha in enumerate(self.alphas):
                    results_array[:, i] = np.array([value > (1 - significance_level) for value in p_value[name]])
            credibility_score[name] = results_array


        #step3 vote
        for name, (method, include_last_label) in self.method_params.items():
            accuracies[name] = accuracy_score(self.y_test, y_preds[name])
            nulls[name] = [self.count_null_set(y_pss[name][:, :, i]) for i, _ in enumerate(self.alphas)]
            coverages[name] = [classification_coverage_score(self.y_test, y_pss[name][:, :, i]) for i, _ in
                               enumerate(self.alphas)]
            confidence_sizes[name] = [y_pss[name][:, :, i].sum(axis=1).mean() for i, _ in enumerate(self.alphas)]
            credibility_sizes[name] = [credibility_score[name][:, i].sum().mean() for i, _ in enumerate(self.alphas)]

        # Find the index of confidence score near 1
        confidence_result = {key: min(range(len(lst)), key=lambda i: abs(lst[i] - 1)) for key, lst in confidence_sizes.items()}
        credibility_result = {key: min(range(len(lst)), key=lambda i: abs(lst[i] - 1)) for key, lst in
                             credibility_sizes.items()}

        # Extract the y_ps at the closest index
        confidence_result_ps = {method: y_pss[method][:, :, confidence_result[method]] for method in y_pss}
        credibility_result_ps = {method: credibility_score[method][:,  credibility_result[method]] for method in credibility_score}
        # Determine indices for each method
        index_all_tem, index_all_right_tem = {}, {}

        for method, y_ps in confidence_result_ps.items():
            for index, i in enumerate(y_ps):
                num_true = sum(i)
                if method not in index_all_tem:
                    index_all_tem[method] = []
                    index_all_right_tem[method] = []
                if num_true != 1:
                    index_all_tem[method].append(index)
                elif num_true == 1:
                    index_all_right_tem[method].append(index)

        index_all = list(set([idx for indices in index_all_tem.values() for idx in indices]))
        index_list = list(index_all_tem.values())
        index_list.append(index_all)

        index_all_right = list(set(range(len(self.y_test))) - set(index_all))
        index_list_right = list(index_all_right_tem.values())
        index_list_right.append(index_all_right)

        """ compute metircs"""
        # o = y[test_index]
        # correct = p == o
        # 所有错误的
        different_indices = np.where(all_pre != y)[0]
        different_indices_right = np.where(all_pre == y)[0]
        # 找到的错误的： index_list
        # 找的真的错的：num_common_elements
        acc_best = 0
        F1_best = 0
        pre_best = 0
        rec_best = 0
        method_name_best = "NONE"
        self.method_params["mixture"] = ("mixture", False)
        print("_____________The MAPIE detection performance can be seen below_____________")
        for index, (single_list, single_list_right) in enumerate(zip(index_list, index_list_right)):
            self.common_elements = np.intersect1d(single_list, different_indices)
            num_common_elements = len(self.common_elements)
            self.common_elements_right = np.intersect1d(single_list_right, different_indices_right)
            num_common_elements_right = len(self.common_elements_right)
            try:
                accuracy = (num_common_elements + num_common_elements_right) / len(all_pre)
            except:
                accuracy = 0
            try:
                precision = num_common_elements / len(single_list)
            except:
                precision = 0
            try:
                recall = num_common_elements / len(different_indices)
            except:
                recall = 0
            try:
                F1 = 2 * precision * recall / (precision + recall)
            except:
                F1 = 0

            print(
                f"The accuracy for detection on {list(self.method_params.keys())[index]} is: {accuracy * 100:.2f}%, "
                f"precision is: {precision * 100:.2f}%, "
                f"recall is: {recall * 100:.2f}%, "
                f"F1 is: {F1 * 100:.2f}%"
            )


            if F1 > F1_best:
                method_name_best = list(self.method_params.keys())[index]
                acc_best = accuracy
                F1_best = F1
                pre_best = precision
                rec_best = recall
        print(
            f"{method_name_best} is the best approach，"
            f"the accuracy is: {accuracy * 100:.2f}%, "
            f"the precision is: {pre_best * 100:.2f}%, "
            f"the recall is: {rec_best * 100:.2f}%, "
            f"the F1 is: {F1_best * 100:.2f}%"
        )
        print("______________________________________")
        Acc_all.append(acc_best)
        F1_all.append(F1_best)
        Pre_all.append(pre_best)
        Rec_all.append(rec_best)

        return 1

    def evaluate_rise(self, y_preds, y_pss,p_value,all_pre,y, significance_level=0.05):
        """
        Evaluates predictions using the RISE method for conformal evaluation.

        Parameters
        ----------
        y_preds : dict
            Predicted labels for each method.

        y_pss : dict
            Prediction sets for each method.

        p_value : dict
            P-values for each method.

        all_pre : array-like
            Array of initial predictions.

        y : array-like
            True labels.

        significance_level : float or str, optional
            Significance level for prediction intervals (default is 0.05).

        Returns
        -------
        tuple
            Evaluation results including accuracy, F1, precision, and recall for each method.
        """
        nulls, coverages, accuracies, confidence_sizes, credibility_sizes = {}, {}, {}, {}, {}
        Acc_all = []
        F1_all = []
        Pre_all = []
        Rec_all = []
        credibility_score={}
        if "mixture" in self.method_params:
            del self.method_params["mixture"]
        for name, (method, include_last_label) in self.method_params.items():
            results_array = np.zeros((len(p_value[name]), len(self.alphas)), dtype=bool)
            #step1, use p-value to select
            if significance_level is "auto":
                for i, alpha in enumerate(self.alphas):
                    results_array[:, i] = np.array([value > (1 - alpha) for value in p_value[name]])
            else:
                for i, alpha in enumerate(self.alphas):
                    results_array[:, i] = np.array([value > (1 - significance_level) for value in p_value[name]])
            credibility_score[name] = results_array


        #step3 vote
        for name, (method, include_last_label) in self.method_params.items():
            accuracies[name] = accuracy_score(self.y_test, y_preds[name])
            nulls[name] = [self.count_null_set(y_pss[name][:, :, i]) for i, _ in enumerate(self.alphas)]
            coverages[name] = [classification_coverage_score(self.y_test, y_pss[name][:, :, i]) for i, _ in
                               enumerate(self.alphas)]
            confidence_sizes[name] = [y_pss[name][:, :, i].sum(axis=1).mean() for i, _ in enumerate(self.alphas)]
            credibility_sizes[name] = [credibility_score[name][:, i].sum().mean() for i, _ in enumerate(self.alphas)]

        # Find the index of confidence score near 1
        confidence_result = {key: min(range(len(lst)), key=lambda i: abs(lst[i] - 1)) for key, lst in confidence_sizes.items()}
        credibility_result = {key: min(range(len(lst)), key=lambda i: abs(lst[i] - 1)) for key, lst in
                             credibility_sizes.items()}

        # Extract the y_ps at the closest index
        confidence_result_ps = {method: y_pss[method][:, :, confidence_result[method]] for method in y_pss}
        credibility_result_ps = {method: credibility_score[method][:,  credibility_result[method]] for method in credibility_score}
        # Determine indices for each method
        index_all_tem, index_all_right_tem = {}, {}


        # for (method, y_ps1), (_, y_ps2) in zip(credibility_result_ps.items(), confidence_result_ps.items()):
        #     for index, confidence_single in enumerate(y_ps2):
        #         confidence_true = sum(confidence_single)
        #         credibility_true = y_ps1[index]
        #         if method not in index_all_tem:
        #             index_all_tem[method] = []
        #             index_all_right_tem[method] = []
        #         if confidence_true == 1 and credibility_true == 1:
        #         # elif confidence_true == 1:
        #             index_all_right_tem[method].append(index)
        #         else:
        #             index_all_tem[method].append(index)
        for method, y_ps in credibility_result_ps.items():
            for index, i in enumerate(y_ps):
                credibility_true = y_ps[index]
                if method not in index_all_tem:
                    index_all_tem[method] = []
                    index_all_right_tem[method] = []
                if credibility_true != 1:
                    index_all_tem[method].append(index)
                elif credibility_true == 1:
                    index_all_right_tem[method].append(index)

        index_all = list(set([idx for indices in index_all_tem.values() for idx in indices]))
        index_list = list(index_all_tem.values())
        index_list.append(index_all)

        index_all_right = list(set(range(len(self.y_test))) - set(index_all))
        index_list_right = list(index_all_right_tem.values())
        index_list_right.append(index_all_right)

        """ compute metircs"""
        # o = y[test_index]
        # correct = p == o
        # 所有错误的
        different_indices = np.where(all_pre != y)[0]
        different_indices_right = np.where(all_pre == y)[0]
        # 找到的错误的： index_list
        # 找的真的错的：num_common_elements
        acc_best = 0
        F1_best = 0
        pre_best = 0
        rec_best = 0
        method_name_best = "NONE"
        self.method_params["mixture"] = ("mixture", False)
        print("_____________The RISE detection performance can be seen below_____________")
        for index, (single_list, single_list_right) in enumerate(zip(index_list, index_list_right)):
            self.common_elements = np.intersect1d(single_list, different_indices)
            num_common_elements = len(self.common_elements)
            self.common_elements_right = np.intersect1d(single_list_right, different_indices_right)
            num_common_elements_right = len(self.common_elements_right)
            try:
                accuracy = (num_common_elements + num_common_elements_right) / len(all_pre)
            except:
                accuracy = 0
            try:
                precision = num_common_elements / len(single_list)
            except:
                precision = 0
            try:
                recall = num_common_elements / len(different_indices)
            except:
                recall = 0
            try:
                F1 = 2 * precision * recall / (precision + recall)
            except:
                F1 = 0

            print(
                f"The accuracy for detection on {list(self.method_params.keys())[index]} is: {accuracy * 100:.2f}%, "
                f"precision is: {precision * 100:.2f}%, "
                f"recall is: {recall * 100:.2f}%, "
                f"F1 is: {F1 * 100:.2f}%"
            )


            if F1 > F1_best:
                method_name_best = list(self.method_params.keys())[index]
                acc_best = accuracy
                F1_best = F1
                pre_best = precision
                rec_best = recall
        print(
            f"{method_name_best} is the best approach，"
            f"the accuracy is: {accuracy * 100:.2f}%, "
            f"the precision is: {pre_best * 100:.2f}%, "
            f"the recall is: {rec_best * 100:.2f}%, "
            f"the F1 is: {F1_best * 100:.2f}%"
        )
        print("______________________________________")
        Acc_all.append(acc_best)
        F1_all.append(F1_best)
        Pre_all.append(pre_best)
        Rec_all.append(rec_best)

        return index_all_right, index_list_right,Acc_all,F1_all,Pre_all,Rec_all,index_list,self.common_elements
