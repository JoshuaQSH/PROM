from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")
from typing import Iterable, Optional, Tuple, Union, cast

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import BaseCrossValidator
from sklearn.pipeline import Pipeline
from sklearn.utils import check_random_state
from sklearn.utils.validation import _check_y, check_is_fitted, indexable
from scipy.stats import gmean, mode,percentileofscore
from src.prom._typing import ArrayLike, NDArray
from src.prom.conformity_scores import ConformityScore, ResidualNormalisedScore
from src.prom.estimator.estimator import EnsembleRegressor
from src.prom.utils import (check_alpha, check_alpha_and_n_samples,
                         check_conformity_score, check_cv,
                         check_estimator_fit_predict, check_n_features_in,
                         check_n_jobs, check_null_weight, check_verbose)
import pandas as pd
import torch
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import pairwise_distances

class MapieRegressor(BaseEstimator, RegressorMixin):
    """
    Prediction interval with out-of-fold conformity scores.

    This class implements the jackknife+ strategy and its variations
    for estimating prediction intervals on single-output data. The
    idea is to evaluate out-of-fold conformity scores (signed residuals,
    absolute residuals, residuals normalized by the predicted mean...)
    on hold-out validation sets and to deduce valid confidence intervals
    with strong theoretical guarantees.

    Parameters
    ----------
    estimator: Optional[RegressorMixin]
        Any regressor with scikit-learn API
        (i.e. with ``fit`` and ``predict`` methods).
        If ``None``, estimator defaults to a ``LinearRegression`` instance.

        By default ``None``.

    method: str
        Method to choose for prediction interval estimates.
        Choose among:

        - ``"naive"``, based on training set conformity scores,
        - ``"base"``, based on validation sets conformity scores,
        - ``"plus"``, based on validation conformity scores and
          testing predictions,
        - ``"minmax"``, based on validation conformity scores and
          testing predictions (min/max among cross-validation clones).

        By default ``"plus"``.

    cv: Optional[Union[int, str, BaseCrossValidator]]
        The cross-validation strategy for computing conformity scores.
        It directly drives the distinction between jackknife and cv variants.
        Choose among:

        - ``None``, to use the default 5-fold cross-validation
        - integer, to specify the number of folds.
          If equal to ``-1``, equivalent to
          ``sklearn.model_selection.LeaveOneOut()``.
        - CV splitter: any ``sklearn.model_selection.BaseCrossValidator``
          Main variants are:
            - ``sklearn.model_selection.LeaveOneOut`` (jackknife),
            - ``sklearn.model_selection.KFold`` (cross-validation),
            - ``subsample.Subsample`` object (bootstrap).
        - ``"split"``, does not involve cross-validation but a division
          of the data into training and calibration subsets. The splitter
          used is the following: ``sklearn.model_selection.ShuffleSplit``.
          ``method`` parameter is set to ``"base"``.
        - ``"prefit"``, assumes that ``estimator`` has been fitted already,
          and the ``method`` parameter is set to ``"base"``.
          All data provided in the ``fit`` method is then used
          for computing conformity scores only.
          At prediction time, quantiles of these conformity scores are used
          to provide a prediction interval with fixed width.
          The user has to take care manually that data for model fitting and
          conformity scores estimate are disjoint.

        By default ``None``.

    test_size: Optional[Union[int, float]]
        If ``float``, should be between ``0.0`` and ``1.0`` and represent the
        proportion of the dataset to include in the test split. If ``int``,
        represents the absolute number of test samples. If ``None``,
        it will be set to ``0.1``.

        If cv is not ``"split"``, ``test_size`` is ignored.

        By default ``None``.

    n_jobs: Optional[int]
        Number of jobs for parallel processing using joblib
        via the "locky" backend.
        If ``-1`` all CPUs are used.
        If ``1`` is given, no parallel computing code is used at all,
        which is useful for debugging.
        For ``n_jobs`` below ``-1``, ``(n_cpus + 1 - n_jobs)`` are used.
        ``None`` is a marker for `unset` that will be interpreted as
        ``n_jobs=1`` (sequential execution).

        By default ``None``.

    agg_function: Optional[str]
        Determines how to aggregate predictions from perturbed models, both at
        training and prediction time.

        If ``None``, it is ignored except if ``cv`` class is ``Subsample``,
        in which case an error is raised.
        If ``"mean"`` or ``"median"``, returns the mean or median of the
        predictions computed from the out-of-folds models.
        Note: if you plan to set the ``ensemble`` argument to ``True`` in the
        ``predict`` method, you have to specify an aggregation function.
        Otherwise an error would be raised.

        The Jackknife+ interval can be interpreted as an interval around the
        median prediction, and is guaranteed to lie inside the interval,
        unlike the single estimator predictions.

        When the cross-validation strategy is ``Subsample`` (i.e. for the
        Jackknife+-after-Bootstrap method), this function is also used to
        aggregate the training set in-sample predictions.

        If ``cv`` is ``"prefit"`` or ``"split"``, ``agg_function`` is ignored.

        By default ``"mean"``.

    verbose: int
        The verbosity level, used with joblib for multiprocessing.
        The frequency of the messages increases with the verbosity level.
        If it more than ``10``, all iterations are reported.
        Above ``50``, the output is sent to stdout.

        By default ``0``.

    conformity_score: Optional[ConformityScore]
        ConformityScore instance.
        It defines the link between the observed values, the predicted ones
        and the conformity scores. For instance, the default ``None`` value
        correspondonds to a conformity score which assumes
        y_obs = y_pred + conformity_score.

        - ``None``, to use the default ``AbsoluteConformityScore`` conformity
          score
        - ConformityScore: any ``ConformityScore`` class

        By default ``None``.

    random_state: Optional[Union[int, RandomState]]
        Pseudo random number generator state used for random sampling.
        Pass an int for reproducible output across multiple function calls.

        By default ``None``.

    Attributes
    ----------
    valid_methods_: List[str]
        List of all valid methods.

    estimator_: EnsembleRegressor
        Sklearn estimator that handle all that is related to the estimator.

    conformity_scores_: ArrayLike of shape (n_samples_train,)
        Conformity scores between ``y_train`` and ``y_pred``.

    n_features_in_: int
        Number of features passed to the ``fit`` method.

    References
    ----------
    Rina Foygel Barber, Emmanuel J. Candès,
    Aaditya Ramdas, and Ryan J. Tibshirani.
    "Predictive inference with the jackknife+."
    Ann. Statist., 49(1):486-507, February 2021.

    Byol Kim, Chen Xu, and Rina Foygel Barber.
    "Predictive Inference Is Free with the Jackknife+-after-Bootstrap."
    34th Conference on Neural Information Processing Systems (NeurIPS 2020).

    Examples
    --------
    >>> import numpy as np
    >>> from mapie.regression import MapieRegressor
    >>> from sklearn.linear_model import LinearRegression
    >>> X_toy = np.array([[0], [1], [2], [3], [4], [5]])
    >>> y_toy = np.array([5, 7.5, 9.5, 10.5, 12.5, 15])
    >>> clf = LinearRegression().fit(X_toy, y_toy)
    >>> mapie_reg = MapieRegressor(estimator=clf, cv="prefit")
    >>> mapie_reg = mapie_reg.fit(X_toy, y_toy)
    >>> y_pred, y_pis = mapie_reg.predict(X_toy, alpha=0.5)
    >>> print(y_pis[:, :, 0])
    [[ 4.95714286  5.61428571]
     [ 6.84285714  7.5       ]
     [ 8.72857143  9.38571429]
     [10.61428571 11.27142857]
     [12.5        13.15714286]
     [14.38571429 15.04285714]]
    >>> print(y_pred)
    [ 5.28571429  7.17142857  9.05714286 10.94285714 12.82857143 14.71428571]
    """

    cv_need_agg_function_ = ["Subsample"]
    no_agg_cv_ = ["prefit", "split"]
    valid_methods_ = ["naive", "base", "plus", "minmax"]
    no_agg_methods_ = ["naive", "base"]
    valid_agg_functions_ = [None, "median", "mean"]
    ensemble_agg_functions_ = ["median", "mean"]
    default_sym_ = True
    fit_attributes = [
        "estimator_",
        "conformity_scores_",
        "conformity_score_function_",
        "n_features_in_",
    ]

    def __init__(
        self,
        estimator: Optional[RegressorMixin] = None,
        method: str = "plus",
        cv: Optional[Union[int, str, BaseCrossValidator]] = None,
        test_size: Optional[Union[int, float]] = None,
        n_jobs: Optional[int] = None,
        agg_function: Optional[str] = "mean",
        verbose: int = 0,
        conformity_score: Optional[ConformityScore] = None,
        random_state: Optional[Union[int, np.random.RandomState]] = None,
    ) -> None:
        self.estimator = estimator
        self.method = method
        self.cv = cv
        self.test_size = test_size
        self.n_jobs = n_jobs
        self.agg_function = agg_function
        self.verbose = verbose
        self.conformity_score = conformity_score
        self.random_state = random_state

    def _check_parameters(self) -> None:
        """
        Perform several checks on input parameters.

        Raises
        ------
        ValueError
            If parameters are not valid.
        """
        self._check_method(self.method)
        check_n_jobs(self.n_jobs)
        check_verbose(self.verbose)
        check_random_state(self.random_state)

    def _check_method(
        self, method: str
    ) -> str:
        """
        Check if ``method`` is correct.

        Parameters
        ----------
        method: str
            Method's name to check.

        Returns
        -------
        str
            ``method`` itself.

        Raises
        ------
        ValueError
            If ``method`` is not in ``self.valid_methods_``.
        """
        if method not in self.valid_methods_:
            raise ValueError(
                f"Invalid method. Allowed values are {self.valid_methods_}."
            )
        else:
            return method

    def _check_agg_function(
        self, agg_function: Optional[str] = None
    ) -> Optional[str]:
        """
        Check if ``agg_function`` is correct, and consistent with other
        arguments.

        Parameters
        ----------
        agg_function: Optional[str]
            Aggregation function's name to check, by default ``None``.

        Returns
        -------
        str
            ``agg_function`` itself or ``"mean"``.

        Raises
        ------
        ValueError
            If ``agg_function`` is not in [``None``, ``"mean"``, ``"median"``],
            or is ``None`` while cv class is in ``cv_need_agg_function_``.
        """
        if agg_function not in self.valid_agg_functions_:
            raise ValueError(
                "Invalid aggregation function. "
                f"Allowed values are '{self.valid_agg_functions_}'."
            )
        elif (agg_function is None) and (
            type(self.cv).__name__ in self.cv_need_agg_function_
        ):
            raise ValueError(
                "You need to specify an aggregation function when "
                f"cv's type is in {self.cv_need_agg_function_}."
            )
        elif agg_function is not None:
            return agg_function
        else:
            return "mean"

    def _check_estimator(
        self, estimator: Optional[RegressorMixin] = None
    ) -> RegressorMixin:
        """
        Check if estimator is ``None``,
        and returns a ``LinearRegression`` instance if necessary.
        If the ``cv`` attribute is ``"prefit"``,
        check if estimator is indeed already fitted.

        Parameters
        ----------
        estimator: Optional[RegressorMixin]
            Estimator to check, by default ``None``.

        Returns
        -------
        RegressorMixin
            The estimator itself or a default ``LinearRegression`` instance.

        Raises
        ------
        ValueError
            If the estimator is not ``None``
            and has no ``fit`` nor ``predict`` methods.

        NotFittedError
            If the estimator is not fitted
            and ``cv`` attribute is ``"prefit"``.
        """
        if estimator is None:
            return LinearRegression()
        else:
            check_estimator_fit_predict(estimator)
            # if self.cv == "prefit":
            #     if isinstance(estimator, Pipeline):
            #         check_is_fitted(estimator[-1])
            #     else:
            #         check_is_fitted(estimator)
            return estimator

    def _check_ensemble(
        self, ensemble: bool,
    ) -> None:
        """
        Check if ``ensemble`` is ``False`` and if ``self.agg_function``
        is ``None``. Else raise error.

        Parameters
        ----------
        ensemble: bool
            ``ensemble`` argument to check the coherennce with
            ``self.agg_function``.

        Raises
        ------
        ValueError
            If ``ensemble`` is ``True`` and ``self.agg_function`` is ``None``.
        """
        if ensemble and (self.agg_function is None):
            raise ValueError(
                "If ensemble is True, the aggregation function has to be "
                f"in '{self.ensemble_agg_functions_}'."
            )

    def _check_fit_parameters(
        self,
        X: ArrayLike,
        y: ArrayLike,
        sample_weight: Optional[ArrayLike] = None,
        groups: Optional[ArrayLike] = None
    ):
        """
        Perform several checks on class parameters.

        Parameters
        ----------
        X: ArrayLike
            Observed values.

        y: ArrayLike
            Target values.

        sample_weight: Optional[NDArray] of shape (n_samples,)
            Non-null sample weights.

        groups: Optional[ArrayLike] of shape (n_samples,)
            Group labels for the samples used while splitting the dataset into
            train/test set.
            By default ``None``.

        Raises
        ------
        ValueError
            If conformity score is FittedResidualNormalizing score and method
            is neither ``"prefit"`` or ``"split"``.

        ValueError
            If ``cv`` is `"prefit"`` or ``"split"`` and ``method`` is not
            ``"base"``.
        """
        # Checking
        self._check_parameters()
        cv = check_cv(
            self.cv, test_size=self.test_size, random_state=self.random_state
        )
        if self.cv in ["split", "prefit"] and self.method != "base":
            self.method = "base"
        estimator = self._check_estimator(self.estimator)
        agg_function = self._check_agg_function(self.agg_function)
        cs_estimator = check_conformity_score(
            self.conformity_score, self.default_sym_
        )
        if isinstance(cs_estimator, ResidualNormalisedScore) and \
           self.cv not in ["split", "prefit"]:
            raise ValueError(
                "The ResidualNormalisedScore can be used only with "
                "``cv='split'`` and ``cv='prefit'``"
            )

        X, y = indexable(X, y)
        y = _check_y(y)
        sample_weight, X, y = check_null_weight(sample_weight, X, y)
        self.n_features_in_ = check_n_features_in(X)

        # Casting
        cv = cast(BaseCrossValidator, cv)
        estimator = cast(RegressorMixin, estimator)
        cs_estimator = cast(ConformityScore, cs_estimator)
        agg_function = cast(Optional[str], agg_function)
        X = cast(NDArray, X)
        y = cast(NDArray, y)
        sample_weight = cast(Optional[NDArray], sample_weight)
        groups = cast(Optional[NDArray], groups)

        return (
            estimator, cs_estimator,
            agg_function, cv,
            X, y,
            sample_weight, groups
        )

    def fit(
        self,
        X: ArrayLike,
        y: ArrayLike,
        sample_weight: Optional[ArrayLike] = None,
        groups: Optional[ArrayLike] = None,
        cluster_num=2,
        **fit_params,
    ) -> MapieRegressor:
        """
        Fit estimator and compute conformity scores used for
        prediction intervals.

        All the types of estimator (single or cross validated ones) are
        encapsulated under EnsembleRegressor.

        Parameters
        ----------
        X: ArrayLike of shape (n_samples, n_features)
            Training data.

        y: ArrayLike of shape (n_samples,)
            Training labels.

        sample_weight: Optional[ArrayLike] of shape (n_samples,)
            Sample weights for fitting the out-of-fold models.
            If ``None``, then samples are equally weighted.
            If some weights are null,
            their corresponding observations are removed
            before the fitting process and hence have no conformity scores.
            If weights are non-uniform,
            conformity scores are still uniformly weighted.

            By default ``None``.

        groups: Optional[ArrayLike] of shape (n_samples,)
            Group labels for the samples used while splitting the dataset into
            train/test set.
            By default ``None``.

        **fit_params : dict
            Additional fit parameters.

        Returns
        -------
        MapieRegressor
            The model itself.
        """
        # Checks
        (estimator,
         self.conformity_score_function_,
         agg_function,
         cv,
         X,
         y,
         sample_weight,
         groups) = self._check_fit_parameters(X, y, sample_weight, groups)

        self.estimator_ = EnsembleRegressor(
            estimator,
            self.method,
            cv,
            agg_function,
            self.n_jobs,
            self.random_state,
            self.test_size,
            self.verbose
        )
        # Fit the prediction function
        self.estimator_ = self.estimator_.fit(
            X, y, sample_weight=sample_weight, groups=groups, **fit_params
        )

        # Predict on calibration data
        y_pred = self.estimator_.predict_calib(X, y=y, groups=groups)
        self.cal = X
        self.cal_y = y
        # Compute the conformity scores (manage jk-ab case)
        self.conformity_scores_ = \
            self.conformity_score_function_.get_conformity_scores(
                X, y, y_pred
            )
        # give the classes for each calibration sample
        self.cal_clusters, self.optimal_k = self.cluster_cal_data(cluster_num)
        return self

    def compute_gap_statistic(self, X, n_refs=5, max_clusters=10):

        gaps = np.zeros(max_clusters - 1)
        results_list = []

        for k in range(1, max_clusters):
            # Holder for reference dispersion results
            ref_disps = np.zeros(n_refs)

            # For n references, generate random sample and perform kmeans getting resulting dispersion of each loop
            for i in range(n_refs):
                random_reference = np.random.random_sample(size=X.shape)
                km = KMeans(n_clusters=k, n_init=10)
                km.fit(random_reference)
                ref_disp = km.inertia_
                ref_disps[i] = ref_disp

            # Fit cluster to original data and create dispersion
            km = KMeans(n_clusters=k)
            km.fit(X)
            orig_disp = km.inertia_

            # Calculate gap statistic
            gap = np.log(np.mean(ref_disps)) - np.log(orig_disp)

            # Assign this loop's gap statistic to gaps
            gaps[k - 1] = gap

            results_list.append({'clusterCount': k, 'gap': gap})
        results_df = pd.DataFrame(results_list)
        return gaps.argmax() + 1, results_df

    def cluster_cal_data(self,cluster_num):
        # Reshape cal to 2D array [n_samples, n_features]
        n_samples = self.cal.size(0)
        feature_dim1 = self.cal.size(1)
        feature_dim2 = self.cal.size(2)
        cal_reshaped = self.cal.view(n_samples, feature_dim1 * feature_dim2).numpy()

        # Determine the optimal number of clusters
        # optimal_k, gap_df = self.compute_gap_statistic(cal_reshaped)
        optimal_k = cluster_num
        # Fit KMeans with the optimal number of clusters
        kmeans = KMeans(n_clusters=optimal_k)
        kmeans.fit(cal_reshaped)

        # Assign each sample in cal to a cluster
        cal_clusters = kmeans.labels_

        return cal_clusters, optimal_k

    def classify_test_samples(self, X, cal_clusters, k=10):
        n_cal_samples = self.cal.size(0)
        n_test_samples = X.size(0)
        feature_dim1 = self.cal.size(1)
        feature_dim2 = self.cal.size(2)

        cal_reshaped = self.cal.view(n_cal_samples, feature_dim1 * feature_dim2)
        X_reshaped = X.view(n_test_samples, feature_dim1 * feature_dim2)

        distances = torch.cdist(X_reshaped, cal_reshaped)
        nearest_indices = torch.topk(distances, k, largest=False, dim=1).indices

        test_clusters = []
        for i in range(n_test_samples):
            nearest_clusters = cal_clusters[nearest_indices[i]]
            test_cluster = mode(nearest_clusters).mode[0]
            test_clusters.append(test_cluster)

        return torch.tensor(test_clusters)

    def compute_residuals(self, X, y_pred):
        n_cal_samples = self.cal.size(0)
        distances = torch.cdist(X.view(X.size(0), -1), self.cal.view(n_cal_samples, -1))
        k = min(max(self.cal.size(0) // 10, 1), 100)
        min_indices = torch.topk(distances, k, largest=False, dim=1).indices
        scores = self.conformity_scores_[min_indices]
        geomean_scores = gmean(scores.numpy(), axis=1)
        true_res = geomean_scores - y_pred.detach().numpy()
        # true_res: the residuals of the estimated test samples
        # geomean_scores: the estimated test samples values
        return true_res,geomean_scores

    def compute_p_values(self, X, cal_clusters,true_res, k=10):
        # 获取每个测试样本的类别
        test_clusters = self.classify_test_samples(X, cal_clusters, k=k)
        # 获取所有类别
        unique_clusters = np.unique(cal_clusters)
        # 为每个测试样本计算每个类别上的p-value
        all_p_values = []
        predicted_p_values = []
        for i in range(X.size(0)):
            p_values = []
            for cluster in unique_clusters:
                # 找到同类别的校准样本
                same_class_indices = torch.nonzero(torch.tensor(cal_clusters) == cluster, as_tuple=True)[0]
                same_class_scores = self.conformity_scores_[same_class_indices]

                # 计算测试样本的分数
                # distances = torch.cdist(X[i].view(1, -1),
                #                         self.cal[same_class_indices].view(same_class_indices.size(0), -1))
                # min_index = torch.argmin(distances).item()
                # test_score = self.conformity_scores_[same_class_indices[min_index]].item()
                test_score = true_res[i]
                # 计算p-value
                p_value = percentileofscore(same_class_scores.numpy(), test_score, kind='mean') / 100.0
                p_values.append(p_value)

            all_p_values.append(p_values)

            # 获取预测类别上的p-value
            predicted_cluster = test_clusters[i].item()
            predicted_p_value = p_values[unique_clusters.tolist().index(predicted_cluster)]
            predicted_p_values.append(predicted_p_value)

        return all_p_values, predicted_p_values

    def predict(
        self,
        X: ArrayLike,
        ensemble: bool = False,
        alpha: Optional[Union[float, Iterable[float]]] = None,
        optimize_beta: bool = False,
        allow_infinite_bounds: bool = False,
    ) -> Union[NDArray, Tuple[NDArray, NDArray]]:
        """
        Predict target on new samples with confidence intervals.
        Conformity scores from the training set and predictions
        from the model clones are central to the computation.
        Prediction Intervals for a given ``alpha`` are deduced from either

        - quantiles of conformity scores (``naive`` and ``base`` methods),
        - quantiles of (predictions +/- conformity scores) (``plus`` method),
        - quantiles of (max/min(predictions) +/- conformity scores)
          (``minmax`` method).

        Parameters
        ----------
        X: ArrayLike of shape (n_samples, n_features)
            Test data.

        ensemble: bool
            Boolean determining whether the predictions are ensembled or not.
            If ``False``, predictions are those of the model trained on the
            whole training set.
            If ``True``, predictions from perturbed models are aggregated by
            the aggregation function specified in the ``agg_function``
            attribute.

            If ``cv`` is ``"prefit"`` or ``"split"``, ``ensemble`` is ignored.

            By default ``False``.

        alpha: Optional[Union[float, Iterable[float]]]
            Can be a float, a list of floats, or a ``ArrayLike`` of floats.
            Between ``0`` and ``1``, represents the uncertainty of the
            confidence interval.
            Lower ``alpha`` produce larger (more conservative) prediction
            intervals.
            ``alpha`` is the complement of the target coverage level.

            By default ``None``.

        optimize_beta: bool
            Whether to optimize the PIs' width or not.

            By default ``False``.

        allow_infinite_bounds: bool
            Allow infinite prediction intervals to be produced.

        Returns
        -------
        Union[NDArray, Tuple[NDArray, NDArray]]
            - NDArray of shape (n_samples,) if ``alpha`` is ``None``.
            - Tuple[NDArray, NDArray] of shapes (n_samples,) and
              (n_samples, 2, n_alpha) if ``alpha`` is not ``None``.
                - [:, 0, :]: Lower bound of the prediction interval.
                - [:, 1, :]: Upper bound of the prediction interval.
        """
        # Checks
        check_is_fitted(self, self.fit_attributes)
        self._check_ensemble(ensemble)
        alpha = cast(Optional[NDArray], check_alpha(alpha))

        if alpha is None:
            y_pred = self.estimator_.predict(
                X, ensemble, return_multi_pred=False
            )
            return np.array(y_pred)

        else:
            if optimize_beta and self.method != 'enbpi':
                warnings.warn(
                    "WARNING: Beta optimisation should only be used for "
                    "method='enbpi'.",
                    UserWarning
                )

            alpha_np = cast(NDArray, alpha)
            if not allow_infinite_bounds:
                n = len(self.conformity_scores_)
                check_alpha_and_n_samples(alpha_np, n)


            y_pred, y_pred_low, y_pred_up = \
                self.conformity_score_function_.get_bounds(
                    X,
                    self.estimator_,
                    self.conformity_scores_,
                    alpha_np,
                    ensemble=ensemble,
                    method=self.method,
                    optimize_beta=optimize_beta
                )
            true_res, geomean_scores = self.compute_residuals(X, y_pred)
            all_p_values, predicted_p_values = self.compute_p_values(X, self.cal_clusters,true_res,k=10)
            # compute the p-value and confidence value
            credibility_scores = predicted_p_values
            confidence_scores = all_p_values

            #
            y_pred_low = np.array(y_pred_low)
            y_pred_up = np.array(y_pred_up)

            # 创建一个三维布尔矩阵来存储结果，形状为 (num_samples, num_confidence_scores, n)
            num_samples = len(geomean_scores)
            # num_confidence_scores = max(len(scores) for scores in geomean_scores if isinstance(scores, (list, np.ndarray)))

            n = y_pred_low.shape[1]

            confidence_result = np.zeros((num_samples, n), dtype=bool)

            for i in range(num_samples):
                sample_confidence = geomean_scores[i]
                sample_low = y_pred_low[i]
                sample_up = y_pred_up[i]

                # for j, score in enumerate(sample_confidence):
                for k in range(n):
                    confidence_result[i, k] = sample_low[k] <= sample_confidence <= sample_up[k]

            # 将结果转换为 numpy 数组以便于后续操作
            confidence_result = np.array(confidence_result)
            # 将 credibility_scores 转换为 NumPy 数组，并变形为 (4000, 1)
            credibility_scores_np = np.array(credibility_scores).reshape(-1, 1)

            # 对比两个数组，生成布尔标志
            credibility_result = credibility_scores_np < alpha_np
            return credibility_result, confidence_result, np.stack([y_pred_low, y_pred_up], axis=1)
            # print("a")
            # select around samples and compute Kmeans as true prediction
            # n_cal_samples = self.cal.size(0)
            # distances = torch.cdist(X.view(X.size(0), -1), self.cal.view(n_cal_samples, -1))  # 展平后计算距离
            # k = min(max(self.cal.size(0) // 10, 1), 100)  # k 是cal大小的1/10，但不超过100
            # min_indices = torch.topk(distances, k, largest=False, dim=1).indices  # 获取最近的k个样本索引
            # scores = self.conformity_scores_[min_indices]  # 根据索引获取分数
            # geomean_scores = gmean(scores, axis=1)  # 计算几何平均数
            # # compute the residuals = true - prediction
            # ture_res = geomean_scores - y_pred.detach().numpy()  # 计算预估残差


            # return np.array(y_pred), np.stack([y_pred_low, y_pred_up], axis=1)
            # test_clusters = self.classify_test_samples(X, self.cal_clusters)
            true_res = self.compute_residuals(X, y_pred)