"""Helper methods."""

import copy
import glob
import errno
import os.path
import time
import calendar
import numpy
import pandas
import matplotlib.colors
from matplotlib import pyplot
import keras
import tensorflow.keras as tf_keras
import tensorflow.keras.layers as layers
import tensorflow.python.keras.backend as K
from scipy.spatial.distance import cdist
from scipy.cluster.hierarchy import linkage, dendrogram
from sklearn.metrics import auc as sklearn_auc
from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet, \
    SGDClassifier
from sklearn.tree import DecisionTreeClassifier, plot_tree
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.cluster import KMeans, AgglomerativeClustering
from cira_ml_short_course.plotting import evaluation_plotting
from cira_ml_short_course.utils import keras_metrics as custom_metrics

# TODO(thunderhoser): Split this into different modules.

# Variable names.
METADATA_COLUMNS = [
    'Step_ID', 'Track_ID', 'Ensemble_Name', 'Ensemble_Member', 'Run_Date',
    'Valid_Date', 'Forecast_Hour', 'Valid_Hour_UTC'
]

EXTRANEOUS_COLUMNS = [
    'Duration', 'Centroid_Lon', 'Centroid_Lat', 'Centroid_X', 'Centroid_Y',
    'Storm_Motion_U', 'Storm_Motion_V', 'Matched', 'Max_Hail_Size',
    'Num_Matches', 'Shape', 'Location', 'Scale'
]

TARGET_NAME = 'RVORT1_MAX-future_max'
BINARIZED_TARGET_NAME = 'strong_future_rotation_flag'

MAE_KEY = 'mean_absolute_error'
RMSE_KEY = 'root_mean_squared_error'
MEAN_BIAS_KEY = 'mean_bias'
MAE_SKILL_SCORE_KEY = 'mae_skill_score'
MSE_SKILL_SCORE_KEY = 'mse_skill_score'

MAX_PEIRCE_SCORE_KEY = 'max_peirce_score'
AUC_KEY = 'area_under_roc_curve'
MAX_CSI_KEY = 'max_csi'
BRIER_SCORE_KEY = 'brier_score'
BRIER_SKILL_SCORE_KEY = 'brier_skill_score'

# Plotting constants.
FIGURE_WIDTH_INCHES = 10
FIGURE_HEIGHT_INCHES = 10
LARGE_FIGURE_WIDTH_INCHES = 15
LARGE_FIGURE_HEIGHT_INCHES = 15

DEFAULT_GRAPH_LINE_COLOUR = numpy.array([27, 158, 119], dtype=float) / 255
DEFAULT_GRAPH_LINE_WIDTH = 2

BAR_GRAPH_COLOUR = numpy.array([27, 158, 119], dtype=float) / 255
BAR_GRAPH_EDGE_WIDTH = 2
BAR_GRAPH_FONT_SIZE = 14
BAR_GRAPH_FONT_COLOUR = numpy.array([217, 95, 2], dtype=float) / 255

GREEN_COLOUR = numpy.array([27, 158, 119], dtype=float) / 255
ORANGE_COLOUR = numpy.array([217, 95, 2], dtype=float) / 255
PURPLE_COLOUR = numpy.array([117, 112, 179], dtype=float) / 255
GREY_COLOUR = numpy.full(3, 152. / 255)

FONT_SIZE = 20
pyplot.rc('font', size=FONT_SIZE)
pyplot.rc('axes', titlesize=FONT_SIZE)
pyplot.rc('axes', labelsize=FONT_SIZE)
pyplot.rc('xtick', labelsize=FONT_SIZE)
pyplot.rc('ytick', labelsize=FONT_SIZE)
pyplot.rc('legend', fontsize=FONT_SIZE)
pyplot.rc('figure', titlesize=FONT_SIZE)

# Misc constants.
DATE_FORMAT = '%Y%m%d'
DATE_FORMAT_REGEX = '[0-9][0-9][0-9][0-9][0-1][0-9][0-3][0-9]'

RANDOM_SEED = 6695
LAMBDA_TOLERANCE = 1e-10

ELU_FUNCTION_NAME = 'elu'
RELU_FUNCTION_NAME = 'relu'
SELU_FUNCTION_NAME = 'selu'
TANH_FUNCTION_NAME = 'tanh'
SIGMOID_FUNCTION_NAME = 'sigmoid'

ACTIVATION_FUNCTION_NAMES = [
    ELU_FUNCTION_NAME, RELU_FUNCTION_NAME, SELU_FUNCTION_NAME,
    TANH_FUNCTION_NAME, SIGMOID_FUNCTION_NAME
]

KERNEL_INITIALIZER_NAME = 'glorot_uniform'
BIAS_INITIALIZER_NAME = 'zeros'

METRIC_FUNCTION_LIST = [
    custom_metrics.accuracy, custom_metrics.binary_accuracy,
    custom_metrics.binary_csi, custom_metrics.binary_frequency_bias,
    custom_metrics.binary_pod, custom_metrics.binary_pofd,
    custom_metrics.binary_peirce_score, custom_metrics.binary_success_ratio,
    custom_metrics.binary_focn
]

# TODO(thunderhoser): Remove word "binary" from these scores.
METRIC_FUNCTION_DICT = {
    'accuracy': custom_metrics.accuracy,
    'binary_accuracy': custom_metrics.binary_accuracy,
    'binary_csi': custom_metrics.binary_csi,
    'binary_frequency_bias': custom_metrics.binary_frequency_bias,
    'binary_pod': custom_metrics.binary_pod,
    'binary_pofd': custom_metrics.binary_pofd,
    'binary_peirce_score': custom_metrics.binary_peirce_score,
    'binary_success_ratio': custom_metrics.binary_success_ratio,
    'binary_focn': custom_metrics.binary_focn
}

DEFAULT_NEURON_COUNTS = numpy.array([1000, 178, 32, 6, 1], dtype=int)
DEFAULT_DROPOUT_RATES = numpy.array([0.5, 0.5, 0.5, 0.5, 0])
DEFAULT_INNER_ACTIV_FUNCTION_NAME = copy.deepcopy(RELU_FUNCTION_NAME)
DEFAULT_INNER_ACTIV_FUNCTION_ALPHA = 0.2
DEFAULT_OUTPUT_ACTIV_FUNCTION_NAME = copy.deepcopy(SIGMOID_FUNCTION_NAME)
DEFAULT_OUTPUT_ACTIV_FUNCTION_ALPHA = 0.
DEFAULT_L1_WEIGHT = 0.
DEFAULT_L2_WEIGHT = 0.001

PLATEAU_PATIENCE_EPOCHS = 5
PLATEAU_LEARNING_RATE_MULTIPLIER = 0.6
PLATEAU_COOLDOWN_EPOCHS = 0
EARLY_STOPPING_PATIENCE_EPOCHS = 10
LOSS_PATIENCE = 0.


def _tabular_file_name_to_date(csv_file_name):
    """Parses date from name of tabular file.

    :param csv_file_name: Path to input file.
    :return: date_string: Date (format "yyyymmdd").
    """

    pathless_file_name = os.path.split(csv_file_name)[-1]
    date_string = pathless_file_name.replace(
        'track_step_NCARSTORM_d01_', ''
    ).replace('-0000.csv', '')

    # Verify.
    time_string_to_unix(time_string=date_string, time_format=DATE_FORMAT)
    return date_string


def _remove_future_data(predictor_table):
    """Removes future data from predictors.

    :param predictor_table: pandas DataFrame with predictor values.  Each row is
        one storm object.
    :return: predictor_table: Same but with fewer columns.
    """

    predictor_names = list(predictor_table)
    columns_to_remove = [p for p in predictor_names if 'future' in p]

    return predictor_table.drop(columns_to_remove, axis=1, inplace=False)


def _lambdas_to_sklearn_inputs(lambda1, lambda2):
    """Converts lambdas to input arguments for scikit-learn.

    :param lambda1: L1-regularization weight.
    :param lambda2: L2-regularization weight.
    :return: alpha: Input arg for scikit-learn model.
    :return: l1_ratio: Input arg for scikit-learn model.
    """

    return lambda1 + lambda2, lambda1 / (lambda1 + lambda2)


def _get_reliability_curve(actual_values, predicted_values, num_bins,
                           max_bin_edge, invert=False):
    """Computes reliability curve for one target variable.

    E = number of examples
    B = number of bins

    :param actual_values: length-E numpy array of actual values.
    :param predicted_values: length-E numpy array of predicted values.
    :param num_bins: Number of bins (points in curve).
    :param max_bin_edge: Value at upper edge of last bin.
    :param invert: Boolean flag.  If True, will return inverted reliability
        curve, which bins by target value and relates target value to
        conditional mean prediction.  If False, will return normal reliability
        curve, which bins by predicted value and relates predicted value to
        conditional mean observation (target).
    :return: mean_predictions: length-B numpy array of x-coordinates.
    :return: mean_observations: length-B numpy array of y-coordinates.
    :return: example_counts: length-B numpy array with num examples in each bin.
    """

    max_bin_edge = max([max_bin_edge, numpy.finfo(float).eps])
    bin_cutoffs = numpy.linspace(0., max_bin_edge, num=num_bins + 1)

    bin_index_by_example = numpy.digitize(
        actual_values if invert else predicted_values, bin_cutoffs, right=False
    ) - 1
    bin_index_by_example[bin_index_by_example < 0] = 0
    bin_index_by_example[bin_index_by_example > num_bins - 1] = num_bins - 1

    mean_predictions = numpy.full(num_bins, numpy.nan)
    mean_observations = numpy.full(num_bins, numpy.nan)
    example_counts = numpy.full(num_bins, -1, dtype=int)

    for i in range(num_bins):
        these_example_indices = numpy.where(bin_index_by_example == i)[0]

        example_counts[i] = len(these_example_indices)
        mean_predictions[i] = numpy.mean(
            predicted_values[these_example_indices]
        )
        mean_observations[i] = numpy.mean(actual_values[these_example_indices])

    return mean_predictions, mean_observations, example_counts


def _add_colour_bar(
        axes_object, colour_map_object, values_to_colour, min_colour_value,
        max_colour_value, colour_norm_object=None,
        orientation_string='vertical', extend_min=True, extend_max=True):
    """Adds colour bar to existing axes.

    :param axes_object: Existing axes (instance of
        `matplotlib.axes._subplots.AxesSubplot`).
    :param colour_map_object: Colour scheme (instance of
        `matplotlib.pyplot.cm`).
    :param values_to_colour: numpy array of values to colour.
    :param min_colour_value: Minimum value in colour scheme.
    :param max_colour_value: Max value in colour scheme.
    :param colour_norm_object: Instance of `matplotlib.colors.BoundaryNorm`,
        defining the scale of the colour map.  If `colour_norm_object is None`,
        will assume that scale is linear.
    :param orientation_string: Orientation of colour bar ("vertical" or
        "horizontal").
    :param extend_min: Boolean flag.  If True, the bottom of the colour bar will
        have an arrow.  If False, it will be a flat line, suggesting that lower
        values are not possible.
    :param extend_max: Same but for top of colour bar.
    :return: colour_bar_object: Colour bar (instance of
        `matplotlib.pyplot.colorbar`) created by this method.
    """

    if colour_norm_object is None:
        colour_norm_object = matplotlib.colors.Normalize(
            vmin=min_colour_value, vmax=max_colour_value, clip=False
        )

    scalar_mappable_object = pyplot.cm.ScalarMappable(
        cmap=colour_map_object, norm=colour_norm_object
    )
    scalar_mappable_object.set_array(values_to_colour)

    if extend_min and extend_max:
        extend_string = 'both'
    elif extend_min:
        extend_string = 'min'
    elif extend_max:
        extend_string = 'max'
    else:
        extend_string = 'neither'

    if orientation_string == 'horizontal':
        padding = 0.075
    else:
        padding = 0.05

    colour_bar_object = pyplot.colorbar(
        ax=axes_object, mappable=scalar_mappable_object,
        orientation=orientation_string, pad=padding, extend=extend_string,
        shrink=0.8
    )

    colour_bar_object.ax.tick_params(labelsize=FONT_SIZE)
    return colour_bar_object


def _get_points_in_roc_curve(observed_labels, forecast_probabilities):
    """Creates points for ROC curve.

    E = number of examples
    T = number of binarization thresholds

    :param observed_labels: length-E numpy array of class labels (integers in
        0...1).
    :param forecast_probabilities: length-E numpy array with forecast
        probabilities of label = 1.
    :return: pofd_by_threshold: length-T numpy array of POFD (probability of
        false detection) values.
    :return: pod_by_threshold: length-T numpy array of POD (probability of
        detection) values.
    """

    assert numpy.all(numpy.logical_or(
        observed_labels == 0, observed_labels == 1
    ))

    assert numpy.all(numpy.logical_and(
        forecast_probabilities >= 0, forecast_probabilities <= 1
    ))

    observed_labels = observed_labels.astype(int)
    binarization_thresholds = numpy.linspace(0, 1, num=1001, dtype=float)

    num_thresholds = len(binarization_thresholds)
    pofd_by_threshold = numpy.full(num_thresholds, numpy.nan)
    pod_by_threshold = numpy.full(num_thresholds, numpy.nan)

    for k in range(num_thresholds):
        these_forecast_labels = (
            forecast_probabilities >= binarization_thresholds[k]
        ).astype(int)

        this_num_hits = numpy.sum(numpy.logical_and(
            these_forecast_labels == 1, observed_labels == 1
        ))

        this_num_false_alarms = numpy.sum(numpy.logical_and(
            these_forecast_labels == 1, observed_labels == 0
        ))

        this_num_misses = numpy.sum(numpy.logical_and(
            these_forecast_labels == 0, observed_labels == 1
        ))

        this_num_correct_nulls = numpy.sum(numpy.logical_and(
            these_forecast_labels == 0, observed_labels == 0
        ))

        try:
            pofd_by_threshold[k] = (
                float(this_num_false_alarms) /
                (this_num_false_alarms + this_num_correct_nulls)
            )
        except ZeroDivisionError:
            pass

        try:
            pod_by_threshold[k] = (
                float(this_num_hits) / (this_num_hits + this_num_misses)
            )
        except ZeroDivisionError:
            pass

    pod_by_threshold = numpy.array([1.] + pod_by_threshold.tolist() + [0.])
    pofd_by_threshold = numpy.array([1.] + pofd_by_threshold.tolist() + [0.])

    return pofd_by_threshold, pod_by_threshold


def _get_points_in_perf_diagram(observed_labels, forecast_probabilities):
    """Creates points for performance diagram.

    E = number of examples
    T = number of binarization thresholds

    :param observed_labels: length-E numpy array of class labels (integers in
        0...1).
    :param forecast_probabilities: length-E numpy array with forecast
        probabilities of label = 1.
    :return: pod_by_threshold: length-T numpy array of POD (probability of
        detection) values.
    :return: success_ratio_by_threshold: length-T numpy array of success ratios.
    """

    assert numpy.all(numpy.logical_or(
        observed_labels == 0, observed_labels == 1
    ))

    assert numpy.all(numpy.logical_and(
        forecast_probabilities >= 0, forecast_probabilities <= 1
    ))

    observed_labels = observed_labels.astype(int)
    binarization_thresholds = numpy.linspace(0, 1, num=1001, dtype=float)

    num_thresholds = len(binarization_thresholds)
    pod_by_threshold = numpy.full(num_thresholds, numpy.nan)
    success_ratio_by_threshold = numpy.full(num_thresholds, numpy.nan)

    for k in range(num_thresholds):
        these_forecast_labels = (
            forecast_probabilities >= binarization_thresholds[k]
        ).astype(int)

        this_num_hits = numpy.sum(numpy.logical_and(
            these_forecast_labels == 1, observed_labels == 1
        ))

        this_num_false_alarms = numpy.sum(numpy.logical_and(
            these_forecast_labels == 1, observed_labels == 0
        ))

        this_num_misses = numpy.sum(numpy.logical_and(
            these_forecast_labels == 0, observed_labels == 1
        ))

        try:
            pod_by_threshold[k] = (
                float(this_num_hits) / (this_num_hits + this_num_misses)
            )
        except ZeroDivisionError:
            pass

        try:
            success_ratio_by_threshold[k] = (
                float(this_num_hits) / (this_num_hits + this_num_false_alarms)
            )
        except ZeroDivisionError:
            pass

    pod_by_threshold = numpy.array([1.] + pod_by_threshold.tolist() + [0.])
    success_ratio_by_threshold = numpy.array(
        [0.] + success_ratio_by_threshold.tolist() + [1.]
    )

    return pod_by_threshold, success_ratio_by_threshold


def _do_activation(input_values, function_name, slope_param=0.2):
    """Runs input array through activation function.

    :param input_values: numpy array (any shape).
    :param function_name: Name of activation function.
    :param slope_param: Slope parameter (alpha) for activation function.  Used
        only for eLU and ReLU.
    :return: output_values: Same as `input_values` but post-activation.
    """

    assert function_name in ACTIVATION_FUNCTION_NAMES

    input_object = K.placeholder()

    if function_name == ELU_FUNCTION_NAME:
        function_object = K.function(
            [input_object],
            [layers.ELU(alpha=slope_param)(input_object)]
        )
    elif function_name == RELU_FUNCTION_NAME:
        function_object = K.function(
            [input_object],
            [layers.LeakyReLU(alpha=slope_param)(input_object)]
        )
    else:
        function_object = K.function(
            [input_object],
            [layers.Activation(function_name)(input_object)]
        )

    return function_object([input_values])[0]


def _get_weight_regularizer(l1_weight, l2_weight):
    """Creates regularizer for neural-net weights.

    :param l1_weight: L1 regularization weight.  This "weight" is not to be
        confused with those being regularized (weights learned by the net).
    :param l2_weight: L2 regularization weight.
    :return: regularizer_object: Instance of `keras.regularizers.l1_l2`.
    """

    l1_weight = numpy.nanmax(numpy.array([l1_weight, 0.]))
    l2_weight = numpy.nanmax(numpy.array([l2_weight, 0.]))

    return keras.regularizers.l1_l2(l1=l1_weight, l2=l2_weight)


def _get_dense_layer(num_output_units, weight_regularizer=None):
    """Creates dense (fully connected) layer.

    :param num_output_units: Number of output units (or "features" or
        "neurons").
    :param weight_regularizer: Will be used to regularize weights in the new
        layer.  This may be instance of `keras.regularizers` or None (if you
        want no regularization).
    :return: layer_object: Instance of `keras.layers.Dense`.
    """

    return keras.layers.Dense(
        num_output_units, activation=None, use_bias=True,
        kernel_initializer=KERNEL_INITIALIZER_NAME,
        bias_initializer=BIAS_INITIALIZER_NAME,
        kernel_regularizer=weight_regularizer,
        bias_regularizer=weight_regularizer
    )


def _get_activation_layer(function_name, slope_param=0.2):
    """Creates activation layer.

    :param function_name: Name of activation function.
    :param slope_param: Slope parameter (alpha) for activation function.  Used
        only for eLU and ReLU.
    :return: layer_object: Instance of `keras.layers.Activation`,
        `keras.layers.ELU`, or `keras.layers.LeakyReLU`.
    """

    assert function_name in ACTIVATION_FUNCTION_NAMES

    if function_name == ELU_FUNCTION_NAME:
        return keras.layers.ELU(alpha=slope_param)

    if function_name == RELU_FUNCTION_NAME:
        if slope_param <= 0:
            return keras.layers.ReLU()

        return keras.layers.LeakyReLU(alpha=slope_param)

    return keras.layers.Activation(function_name)


def _get_dropout_layer(dropout_fraction):
    """Creates dropout layer.

    :param dropout_fraction: Fraction of weights to drop.
    :return: layer_object: Instance of `keras.layers.Dropout`.
    """

    assert dropout_fraction > 0.
    assert dropout_fraction < 1.

    return keras.layers.Dropout(rate=dropout_fraction)


def _get_batch_norm_layer():
    """Creates batch-normalization layer.

    :return: Instance of `keras.layers.BatchNormalization`.
    """

    return keras.layers.BatchNormalization(
        axis=-1, momentum=0.99, epsilon=0.001, center=True, scale=True
    )


def _mkdir_recursive_if_necessary(directory_name=None, file_name=None):
    """Creates directory if necessary (i.e., doesn't already exist).

    This method checks for the argument `directory_name` first.  If
    `directory_name` is None, this method checks for `file_name` and extracts
    the directory.

    :param directory_name: Path to local directory.
    :param file_name: Path to local file.
    """

    if directory_name is None:
        directory_name = os.path.dirname(file_name)
    if directory_name == '':
        return

    try:
        os.makedirs(directory_name)
    except OSError as this_error:
        if this_error.errno == errno.EEXIST and os.path.isdir(directory_name):
            pass
        else:
            raise


def create_paneled_figure(
        num_rows, num_columns, figure_width_inches=FIGURE_WIDTH_INCHES,
        figure_height_inches=FIGURE_HEIGHT_INCHES,
        horizontal_spacing=0.075, vertical_spacing=0., shared_x_axis=False,
        shared_y_axis=False, keep_aspect_ratio=True):
    """Creates paneled figure.

    This method only initializes the panels.  It does not plot anything.

    J = number of panel rows
    K = number of panel columns

    :param num_rows: J in the above discussion.
    :param num_columns: K in the above discussion.
    :param figure_width_inches: Width of the entire figure (including all
        panels).
    :param figure_height_inches: Height of the entire figure (including all
        panels).
    :param horizontal_spacing: Spacing (in figure-relative coordinates, from
        0...1) between adjacent panel columns.
    :param vertical_spacing: Spacing (in figure-relative coordinates, from
        0...1) between adjacent panel rows.
    :param shared_x_axis: Boolean flag.  If True, all panels will share the same
        x-axis.
    :param shared_y_axis: Boolean flag.  If True, all panels will share the same
        y-axis.
    :param keep_aspect_ratio: Boolean flag.  If True, the aspect ratio of each
        panel will be preserved (reflect the aspect ratio of the data plotted
        therein).
    :return: figure_object: Figure handle (instance of
        `matplotlib.figure.Figure`).
    :return: axes_object_matrix: J-by-K numpy array of axes handles (instances
        of `matplotlib.axes._subplots.AxesSubplot`).
    """

    figure_object, axes_object_matrix = pyplot.subplots(
        num_rows, num_columns, sharex=shared_x_axis, sharey=shared_y_axis,
        figsize=(figure_width_inches, figure_height_inches)
    )

    if num_rows == num_columns == 1:
        axes_object_matrix = numpy.full(
            (1, 1), axes_object_matrix, dtype=object
        )

    if num_rows == 1 or num_columns == 1:
        axes_object_matrix = numpy.reshape(
            axes_object_matrix, (num_rows, num_columns)
        )

    pyplot.subplots_adjust(
        left=0.02, bottom=0.02, right=0.98, top=0.95,
        hspace=horizontal_spacing, wspace=vertical_spacing
    )

    if not keep_aspect_ratio:
        return figure_object, axes_object_matrix

    for i in range(num_rows):
        for j in range(num_columns):
            axes_object_matrix[i][j].set(aspect='equal')

    return figure_object, axes_object_matrix


def time_string_to_unix(time_string, time_format):
    """Converts time from string to Unix format.

    Unix format = seconds since 0000 UTC 1 Jan 1970.

    :param time_string: Time string.
    :param time_format: Format of time string (example: "%Y%m%d" or
        "%Y-%m-%d-%H%M%S").
    :return: unix_time_sec: Time in Unix format.
    """

    return calendar.timegm(time.strptime(time_string, time_format))


def time_unix_to_string(unix_time_sec, time_format):
    """Converts time from Unix format to string.

    Unix format = seconds since 0000 UTC 1 Jan 1970.

    :param unix_time_sec: Time in Unix format.
    :param time_format: Desired format of time string (example: "%Y%m%d" or
        "%Y-%m-%d-%H%M%S").
    :return: time_string: Time string.
    """

    return time.strftime(time_format, time.gmtime(unix_time_sec))


def find_tabular_files(directory_name, first_date_string, last_date_string):
    """Finds CSV files with tabular data.

    :param directory_name: Name of directory with tabular files.
    :param first_date_string: First date ("yyyymmdd") in range.
    :param last_date_string: Last date ("yyyymmdd") in range.
    :return: csv_file_names: 1-D list of paths to tabular files.
    """

    first_time_unix_sec = time_string_to_unix(
        time_string=first_date_string, time_format=DATE_FORMAT
    )
    last_time_unix_sec = time_string_to_unix(
        time_string=last_date_string, time_format=DATE_FORMAT
    )

    csv_file_pattern = '{0:s}/track_step_NCARSTORM_d01_{1:s}-0000.csv'.format(
        directory_name, DATE_FORMAT_REGEX
    )
    csv_file_names = glob.glob(csv_file_pattern)
    csv_file_names.sort()

    file_date_strings = [_tabular_file_name_to_date(f) for f in csv_file_names]

    file_times_unix_sec = numpy.array([
        time_string_to_unix(time_string=d, time_format=DATE_FORMAT)
        for d in file_date_strings
    ], dtype=int)

    good_indices = numpy.where(numpy.logical_and(
        file_times_unix_sec >= first_time_unix_sec,
        file_times_unix_sec <= last_time_unix_sec
    ))[0]

    return [csv_file_names[k] for k in good_indices]


def read_tabular_file(csv_file_name):
    """Reads tabular data from CSV file.

    :param csv_file_name: Path to input file.
    :return: metadata_table: pandas DataFrame with metadata.  Each row is one
        storm object.
    :return: predictor_table: pandas DataFrame with predictor values.  Each row
        is one storm object.
    :return: target_table: pandas DataFrame with target values.  Each row is one
        storm object.
    """

    predictor_table = pandas.read_csv(csv_file_name, header=0, sep=',')
    predictor_table.drop(EXTRANEOUS_COLUMNS, axis=1, inplace=True)

    metadata_table = predictor_table[METADATA_COLUMNS]
    predictor_table.drop(METADATA_COLUMNS, axis=1, inplace=True)

    target_table = predictor_table[[TARGET_NAME]]
    predictor_table.drop([TARGET_NAME], axis=1, inplace=True)
    predictor_table = _remove_future_data(predictor_table)

    return metadata_table, predictor_table, target_table


def read_many_tabular_files(csv_file_names):
    """Reads tabular data from many CSV files.

    :param csv_file_names: 1-D list of paths to input files.
    :return: metadata_table: See doc for `read_tabular_file`.
    :return: predictor_table: Same.
    :return: target_table: Same.
    """

    num_files = len(csv_file_names)
    list_of_metadata_tables = [pandas.DataFrame()] * num_files
    list_of_predictor_tables = [pandas.DataFrame()] * num_files
    list_of_target_tables = [pandas.DataFrame()] * num_files

    for i in range(num_files):
        print('Reading data from: "{0:s}"...'.format(csv_file_names[i]))

        (list_of_metadata_tables[i], list_of_predictor_tables[i],
         list_of_target_tables[i]
        ) = read_tabular_file(csv_file_names[i])

        if i == 0:
            continue

        list_of_metadata_tables[i] = list_of_metadata_tables[i].align(
            list_of_metadata_tables[0], axis=1
        )[0]

        list_of_predictor_tables[i] = list_of_predictor_tables[i].align(
            list_of_predictor_tables[0], axis=1
        )[0]

        list_of_target_tables[i] = list_of_target_tables[i].align(
            list_of_target_tables[0], axis=1
        )[0]

    metadata_table = pandas.concat(
        list_of_metadata_tables, axis=0, ignore_index=True
    )
    predictor_table = pandas.concat(
        list_of_predictor_tables, axis=0, ignore_index=True
    )
    target_table = pandas.concat(
        list_of_target_tables, axis=0, ignore_index=True
    )

    return metadata_table, predictor_table, target_table


def normalize_predictors(predictor_table, normalization_dict=None):
    """Normalizes predictors to z-scores.

    :param predictor_table: See doc for `read_tabular_file`.
    :param normalization_dict: Dictionary.  Each key is the name of a predictor
        value, and the corresponding value is a length-2 numpy array with
        [mean, standard deviation].  If `normalization_dict is None`, mean and
        standard deviation will be computed for each predictor.
    :return: predictor_table: Normalized version of input.
    :return: normalization_dict: See doc for input variable.  If input was None,
        this will be a newly created dictionary.  Otherwise, this will be the
        same dictionary passed as input.
    """

    predictor_names = list(predictor_table)
    num_predictors = len(predictor_names)

    if normalization_dict is None:
        normalization_dict = {}

        for m in range(num_predictors):
            this_mean = numpy.mean(predictor_table[predictor_names[m]].values)
            this_stdev = numpy.std(
                predictor_table[predictor_names[m]].values, ddof=1
            )

            normalization_dict[predictor_names[m]] = numpy.array(
                [this_mean, this_stdev]
            )

    for m in range(num_predictors):
        this_mean = normalization_dict[predictor_names[m]][0]
        this_stdev = normalization_dict[predictor_names[m]][1]
        these_norm_values = (
            (predictor_table[predictor_names[m]].values - this_mean) /
            this_stdev
        )

        predictor_table = predictor_table.assign(**{
            predictor_names[m]: these_norm_values
        })

    return predictor_table, normalization_dict


def denormalize_predictors(predictor_table, normalization_dict):
    """Denormalizes predictors from z-scores back to original scales.

    :param predictor_table: See doc for `normalize_predictors`.
    :param normalization_dict: Same.
    :return: predictor_table: Denormalized version of input.
    """

    predictor_names = list(predictor_table)
    num_predictors = len(predictor_names)

    for m in range(num_predictors):
        this_mean = normalization_dict[predictor_names[m]][0]
        this_stdev = normalization_dict[predictor_names[m]][1]
        these_denorm_values = (
            this_mean + this_stdev * predictor_table[predictor_names[m]].values
        )

        predictor_table = predictor_table.assign(**{
            predictor_names[m]: these_denorm_values
        })

    return predictor_table


def setup_linear_regression(lambda1=0., lambda2=0.):
    """Sets up (but does not train) linear-regression model.

    :param lambda1: L1-regularization weight.
    :param lambda2: L2-regularization weight.
    :return: model_object: Instance of `sklearn.linear_model`.
    """

    assert lambda1 >= 0
    assert lambda2 >= 0

    if lambda1 < LAMBDA_TOLERANCE and lambda2 < LAMBDA_TOLERANCE:
        return LinearRegression(fit_intercept=True, normalize=False)

    if lambda1 < LAMBDA_TOLERANCE:
        return Ridge(
            alpha=lambda2, fit_intercept=True, normalize=False,
            random_state=RANDOM_SEED
        )

    if lambda2 < LAMBDA_TOLERANCE:
        return Lasso(
            alpha=lambda1, fit_intercept=True, normalize=False,
            random_state=RANDOM_SEED
        )

    alpha, l1_ratio = _lambdas_to_sklearn_inputs(
        lambda1=lambda1, lambda2=lambda2
    )

    return ElasticNet(
        alpha=alpha, l1_ratio=l1_ratio, fit_intercept=True, normalize=False,
        random_state=RANDOM_SEED
    )


def train_linear_regression(model_object, training_predictor_table,
                            training_target_table):
    """Trains linear-regression model.

    :param model_object: Untrained model created by `setup_linear_regression`.
    :param training_predictor_table: See doc for `read_tabular_file`.
    :param training_target_table: Same.
    :return: model_object: Trained version of input.
    """

    model_object.fit(
        X=training_predictor_table.to_numpy(),
        y=training_target_table[TARGET_NAME].values
    )

    return model_object


def evaluate_regression(
        actual_values, predicted_values, mean_training_target_value,
        verbose=True, create_plots=True, dataset_name=None):
    """Evaluates regression model.

    E = number of examples

    :param actual_values: length-E numpy array of actual target values.
    :param predicted_values: length-E numpy array of predictions.
    :param mean_training_target_value: Mean target value in training data.
    :param verbose: Boolean flag.  If True, will print results to command
        window.
    :param create_plots: Boolean flag.  If True, will create plots.
    :param dataset_name: Dataset name (e.g., "validation").  Used only if
        `create_plots == True or verbose == True`.
    :return: evaluation_dict: Dictionary with the following keys.
    evaluation_dict['mean_absolute_error']: Mean absolute error (MAE).
    evaluation_dict['rmse']: Root mean squared error (RMSE).
    evaluation_dict['mean_bias']: Mean bias (signed error).
    evaluation_dict['mae_skill_score']: MAE skill score (fractional improvement
        over climatology, in range -1...1).
    evaluation_dict['mse_skill_score']: MSE skill score (fractional improvement
        over climatology, in range -1...1).
    """

    signed_errors = predicted_values - actual_values
    mean_bias = numpy.mean(signed_errors)
    mean_absolute_error = numpy.mean(numpy.absolute(signed_errors))
    rmse = numpy.sqrt(numpy.mean(signed_errors ** 2))

    climo_signed_errors = mean_training_target_value - actual_values
    climo_mae = numpy.mean(numpy.absolute(climo_signed_errors))
    climo_mse = numpy.mean(climo_signed_errors ** 2)

    mae_skill_score = (climo_mae - mean_absolute_error) / climo_mae
    mse_skill_score = (climo_mse - rmse ** 2) / climo_mse

    evaluation_dict = {
        MAE_KEY: mean_absolute_error,
        RMSE_KEY: rmse,
        MEAN_BIAS_KEY: mean_bias,
        MAE_SKILL_SCORE_KEY: mae_skill_score,
        MSE_SKILL_SCORE_KEY: mse_skill_score
    }

    if verbose or create_plots:
        dataset_name = dataset_name[0].upper() + dataset_name[1:]

    if verbose:
        print('{0:s} MAE (mean absolute error) = {1:.3e} s^-1'.format(
            dataset_name, evaluation_dict[MAE_KEY]
        ))
        print('{0:s} MSE (mean squared error) = {1:.3e} s^-2'.format(
            dataset_name, evaluation_dict[RMSE_KEY]
        ))
        print('{0:s} bias (mean signed error) = {1:.3e} s^-1'.format(
            dataset_name, evaluation_dict[MEAN_BIAS_KEY]
        ))

        message_string = (
            '{0:s} MAE skill score (improvement over climatology) = {1:.3f}'
        ).format(dataset_name, evaluation_dict[MAE_SKILL_SCORE_KEY])
        print(message_string)

        message_string = (
            '{0:s} MSE skill score (improvement over climatology) = {1:.3f}'
        ).format(dataset_name, evaluation_dict[MSE_SKILL_SCORE_KEY])
        print(message_string)

    if not create_plots:
        return evaluation_dict

    mean_predictions, mean_observations, example_counts = (
        _get_reliability_curve(
            actual_values=actual_values, predicted_values=predicted_values,
            num_bins=20, max_bin_edge=numpy.percentile(predicted_values, 99),
            invert=False
        )
    )

    inv_mean_observations, inv_example_counts = (
        _get_reliability_curve(
            actual_values=actual_values, predicted_values=predicted_values,
            num_bins=20, max_bin_edge=numpy.percentile(actual_values, 99),
            invert=True
        )[1:]
    )

    concat_values = numpy.concatenate((mean_predictions, mean_observations))

    figure_object, axes_object = pyplot.subplots(
        1, 1, figsize=(FIGURE_WIDTH_INCHES, FIGURE_HEIGHT_INCHES)
    )

    evaluation_plotting.plot_attributes_diagram(
        figure_object=figure_object, axes_object=axes_object,
        mean_predictions=mean_predictions, mean_observations=mean_observations,
        example_counts=example_counts,
        inv_mean_observations=inv_mean_observations,
        inv_example_counts=inv_example_counts,
        mean_value_in_training=mean_training_target_value,
        min_value_to_plot=0., max_value_to_plot=numpy.max(concat_values)
    )

    axes_object.set_xlabel(r'Forecast value (s$^{-1}$)')
    axes_object.set_ylabel(r'Conditional mean observation (s$^{-1}$)')

    title_string = '{0:s} attributes diagram for max future vorticity'.format(
        dataset_name
    )
    axes_object.set_title(title_string)
    pyplot.show()

    return evaluation_dict


def plot_model_coefficients(model_object, predictor_names):
    """Plots coefficients for linear- or logistic-regression model.

    :param model_object: Trained instance of `sklearn.linear_model`.
    :param predictor_names: 1-D list of predictor names, in the same order used
        to train the model.
    """

    coefficients = model_object.coef_
    num_dimensions = len(coefficients.shape)
    if num_dimensions > 1:
        coefficients = coefficients[0, ...]

    num_predictors = len(predictor_names)
    y_coords = numpy.linspace(
        0, num_predictors - 1, num=num_predictors, dtype=float
    )

    _, axes_object = pyplot.subplots(
        1, 1, figsize=(FIGURE_WIDTH_INCHES, FIGURE_HEIGHT_INCHES)
    )

    axes_object.barh(
        y_coords, coefficients, color=BAR_GRAPH_COLOUR,
        edgecolor=BAR_GRAPH_COLOUR, linewidth=BAR_GRAPH_EDGE_WIDTH
    )

    pyplot.xlabel('Coefficient')
    pyplot.ylabel('Predictor variable')

    pyplot.yticks([], [])
    x_tick_values, _ = pyplot.xticks()
    pyplot.xticks(x_tick_values, rotation=90)

    x_min = numpy.percentile(coefficients, 1.)
    x_max = numpy.percentile(coefficients, 99.)
    pyplot.xlim([x_min, x_max])

    for j in range(num_predictors):
        axes_object.text(
            0, y_coords[j], predictor_names[j], color=BAR_GRAPH_FONT_COLOUR,
            horizontalalignment='center', verticalalignment='center',
            fontsize=BAR_GRAPH_FONT_SIZE
        )


def plot_scores_2d(
        score_matrix, min_colour_value, max_colour_value, x_tick_labels,
        y_tick_labels, colour_map_object=pyplot.get_cmap('plasma')
):
    """Plots scores on 2-D grid.

    M = number of rows in grid
    N = number of columns in grid

    :param score_matrix: M-by-N numpy array of scores.
    :param min_colour_value: Minimum value in colour scheme.
    :param max_colour_value: Max value in colour scheme.
    :param x_tick_labels: length-N list of tick labels.
    :param y_tick_labels: length-M list of tick labels.
    :param colour_map_object: Colour scheme (instance of
        `matplotlib.pyplot.cm`).
    """

    _, axes_object = pyplot.subplots(
        1, 1, figsize=(FIGURE_WIDTH_INCHES, FIGURE_HEIGHT_INCHES)
    )

    pyplot.imshow(
        score_matrix, cmap=colour_map_object, origin='lower',
        vmin=min_colour_value, vmax=max_colour_value
    )

    x_tick_values = numpy.linspace(
        0, score_matrix.shape[1] - 1, num=score_matrix.shape[1], dtype=float
    )
    y_tick_values = numpy.linspace(
        0, score_matrix.shape[0] - 1, num=score_matrix.shape[0], dtype=float
    )

    pyplot.xticks(x_tick_values, x_tick_labels)
    pyplot.yticks(y_tick_values, y_tick_labels)

    _add_colour_bar(
        axes_object=axes_object, colour_map_object=colour_map_object,
        values_to_colour=score_matrix, min_colour_value=min_colour_value,
        max_colour_value=max_colour_value
    )


def plot_scores_1d(
        score_values, x_tick_labels, line_colour=DEFAULT_GRAPH_LINE_COLOUR,
        line_width=DEFAULT_GRAPH_LINE_WIDTH):
    """Plots scores on a 1-D graph.

    N = number of values

    :param score_values: length-N numpy array of scores.
    :param x_tick_labels: length-N list of tick labels.
    :param line_colour: Line colour (ideally a length-3 numpy array).
    :param line_width: Line width.
    """

    _, axes_object = pyplot.subplots(
        1, 1, figsize=(FIGURE_WIDTH_INCHES, FIGURE_HEIGHT_INCHES)
    )

    num_values = len(score_values)
    x_tick_values = numpy.linspace(
        0, num_values - 1, num=num_values, dtype=float
    )

    axes_object.plot(
        x_tick_values, score_values, color=line_colour, linestyle='solid',
        linewidth=line_width
    )

    pyplot.xticks(x_tick_values, x_tick_labels)


def get_binarization_threshold(tabular_file_names, percentile_level):
    """Computes binarization threshold for target variable.

    Binarization threshold will be [q]th percentile of all target values, where
    q = `percentile_level`.

    :param tabular_file_names: 1-D list of paths to input files.
    :param percentile_level: q in the above discussion.
    :return: binarization_threshold: Binarization threshold (used to turn each
        target value into a yes-or-no label).
    """

    max_target_values = numpy.array([])

    for this_file_name in tabular_file_names:
        print('Reading data from: "{0:s}"...'.format(this_file_name))
        this_target_table = read_tabular_file(this_file_name)[-1]

        max_target_values = numpy.concatenate((
            max_target_values, this_target_table[TARGET_NAME].values
        ))

    binarization_threshold = numpy.percentile(
        max_target_values, percentile_level)

    print('\nBinarization threshold for "{0:s}" = {1:.4e}'.format(
        TARGET_NAME, binarization_threshold
    ))

    return binarization_threshold


def binarize_target_values(target_values, binarization_threshold):
    """Binarizes target values.

    E = number of examples (storm objects)

    :param target_values: length-E numpy array of real-number target values.
    :param binarization_threshold: Binarization threshold.
    :return: target_values: length-E numpy array of binarized target values
        (integers in 0...1).
    """

    return (target_values >= binarization_threshold).astype(int)


def setup_logistic_regression(lambda1=0., lambda2=0.):
    """Sets up (but does not train) logistic-regression model.

    :param lambda1: L1-regularization weight.
    :param lambda2: L2-regularization weight.
    :return: model_object: Instance of `sklearn.linear_model.SGDClassifier`.
    """

    assert lambda1 >= 0
    assert lambda2 >= 0

    if lambda1 < LAMBDA_TOLERANCE and lambda2 < LAMBDA_TOLERANCE:
        return SGDClassifier(
            loss='log', penalty='none', fit_intercept=True, verbose=0,
            random_state=RANDOM_SEED
        )

    if lambda1 < LAMBDA_TOLERANCE:
        return SGDClassifier(
            loss='log', penalty='l2', alpha=lambda2, fit_intercept=True,
            verbose=0, random_state=RANDOM_SEED
        )

    if lambda2 < LAMBDA_TOLERANCE:
        return SGDClassifier(
            loss='log', penalty='l1', alpha=lambda1, fit_intercept=True,
            verbose=0, random_state=RANDOM_SEED
        )

    alpha, l1_ratio = _lambdas_to_sklearn_inputs(
        lambda1=lambda1, lambda2=lambda2
    )

    return SGDClassifier(
        loss='log', penalty='elasticnet', alpha=alpha, l1_ratio=l1_ratio,
        fit_intercept=True, verbose=0, random_state=RANDOM_SEED
    )


def train_logistic_regression(model_object, training_predictor_table,
                              training_target_table):
    """Trains logistic-regression model.

    :param model_object: Untrained model created by `setup_logistic_regression`.
    :param training_predictor_table: See doc for `read_tabular_file`.
    :param training_target_table: Same.
    :return: model_object: Trained version of input.
    """

    model_object.fit(
        X=training_predictor_table.to_numpy(),
        y=training_target_table[BINARIZED_TARGET_NAME].values
    )

    return model_object


def eval_binary_classifn(
        observed_labels, forecast_probabilities, training_event_frequency,
        verbose=True, create_plots=True, dataset_name=None):
    """Evaluates binary-classification model.

    E = number of examples

    :param observed_labels: length-E numpy array of observed labels (integers in
        0...1, where 1 means that event occurred).
    :param forecast_probabilities: length-E numpy array with forecast
        probabilities of event (positive class).
    :param training_event_frequency: Frequency of event in training data.
    :param verbose: Boolean flag.  If True, will print results to command
        window.
    :param create_plots: Boolean flag.  If True, will create plots.
    :param dataset_name: Dataset name (e.g., "validation").  Used only if
        `create_plots == True or verbose == True`.
    """

    if verbose or create_plots:
        assert dataset_name is not None
        dataset_name = dataset_name[0].upper() + dataset_name[1:]

    # Plot ROC curve.
    pofd_by_threshold, pod_by_threshold = _get_points_in_roc_curve(
        observed_labels=observed_labels,
        forecast_probabilities=forecast_probabilities
    )
    max_peirce_score = numpy.nanmax(pod_by_threshold - pofd_by_threshold)
    area_under_roc_curve = sklearn_auc(x=pofd_by_threshold, y=pod_by_threshold)

    if create_plots:
        _, axes_object = pyplot.subplots(
            1, 1, figsize=(FIGURE_WIDTH_INCHES, FIGURE_HEIGHT_INCHES)
        )

        evaluation_plotting.plot_roc_curve(
            axes_object=axes_object,
            pod_by_threshold=pod_by_threshold,
            pofd_by_threshold=pofd_by_threshold
        )

        title_string = '{0:s} ROC curve (AUC = {1:.3f})'.format(
            dataset_name, area_under_roc_curve
        )
        axes_object.set_title(title_string)

    pod_by_threshold, success_ratio_by_threshold = _get_points_in_perf_diagram(
        observed_labels=observed_labels,
        forecast_probabilities=forecast_probabilities
    )
    csi_by_threshold = (
        (pod_by_threshold ** -1 + success_ratio_by_threshold ** -1 - 1) ** -1
    )
    max_csi = numpy.nanmax(csi_by_threshold)

    if create_plots:
        _, axes_object = pyplot.subplots(
            1, 1, figsize=(FIGURE_WIDTH_INCHES, FIGURE_HEIGHT_INCHES)
        )

        evaluation_plotting.plot_performance_diagram(
            axes_object=axes_object,
            pod_by_threshold=pod_by_threshold,
            success_ratio_by_threshold=success_ratio_by_threshold
        )

        title_string = '{0:s} performance diagram (max CSI = {1:.3f})'.format(
            dataset_name, max_csi
        )
        axes_object.set_title(title_string)

    mean_forecast_probs, event_frequencies, example_counts = (
        _get_reliability_curve(
            actual_values=observed_labels.astype(float),
            predicted_values=forecast_probabilities,
            num_bins=20, max_bin_edge=1., invert=False
        )
    )

    uncertainty = training_event_frequency * (1. - training_event_frequency)
    this_numerator = numpy.nansum(
        example_counts * (mean_forecast_probs - event_frequencies) ** 2
    )
    reliability = this_numerator / numpy.sum(example_counts)

    this_numerator = numpy.nansum(
        example_counts * (event_frequencies - training_event_frequency) ** 2
    )
    resolution = this_numerator / numpy.sum(example_counts)

    brier_score = uncertainty + reliability - resolution
    brier_skill_score = (resolution - reliability) / uncertainty

    if create_plots:
        figure_object, axes_object = pyplot.subplots(
            1, 1, figsize=(FIGURE_WIDTH_INCHES, FIGURE_HEIGHT_INCHES)
        )

        evaluation_plotting.plot_attributes_diagram(
            figure_object=figure_object, axes_object=axes_object,
            mean_predictions=mean_forecast_probs,
            mean_observations=event_frequencies,
            example_counts=example_counts,
            mean_value_in_training=training_event_frequency,
            min_value_to_plot=0., max_value_to_plot=1.
        )

        axes_object.set_xlabel(r'Forecast probability')
        axes_object.set_ylabel(r'Conditional event frequency')

        title_string = '{0:s} attributes diagram (BSS = {1:.3f})'.format(
            dataset_name, brier_skill_score
        )
        axes_object.set_title(title_string)
        pyplot.show()

    evaluation_dict = {
        MAX_PEIRCE_SCORE_KEY: max_peirce_score,
        AUC_KEY: area_under_roc_curve,
        MAX_CSI_KEY: max_csi,
        BRIER_SCORE_KEY: brier_score,
        BRIER_SKILL_SCORE_KEY: brier_skill_score
    }

    if verbose:
        print('{0:s} max Peirce score (POD - POFD) = {1:.3f}'.format(
            dataset_name, evaluation_dict[MAX_PEIRCE_SCORE_KEY]
        ))
        print('{0:s} AUC (area under ROC curve) = {1:.3f}'.format(
            dataset_name, evaluation_dict[AUC_KEY]
        ))
        print('{0:s} max CSI (critical success index) = {1:.3f}'.format(
            dataset_name, evaluation_dict[MAX_CSI_KEY]
        ))
        print('{0:s} Brier score = {1:.3f}'.format(
            dataset_name, evaluation_dict[BRIER_SCORE_KEY]
        ))

        message_string = (
            '{0:s} Brier skill score (improvement over climatology) = {1:.3f}'
        ).format(dataset_name, evaluation_dict[BRIER_SKILL_SCORE_KEY])
        print(message_string)

    return evaluation_dict


def setup_classification_tree(
        min_examples_at_split=30, min_examples_at_leaf=30):
    """Sets up (but does not train) decision tree for classification.

    :param min_examples_at_split: Minimum number of examples at split node.
    :param min_examples_at_leaf: Minimum number of examples at leaf node.
    :return: model_object: Instance of `sklearn.tree.DecisionTreeClassifier`.
    """

    return DecisionTreeClassifier(
        criterion='entropy', min_samples_split=min_examples_at_split,
        min_samples_leaf=min_examples_at_leaf, random_state=RANDOM_SEED
    )


def train_classification_tree(model_object, training_predictor_table,
                              training_target_table):
    """Trains decision tree for classification.

    :param model_object: Untrained model created by `setup_classification_tree`.
    :param training_predictor_table: See doc for `read_tabular_file`.
    :param training_target_table: Same.
    :return: model_object: Trained version of input.
    """

    model_object.fit(
        X=training_predictor_table.to_numpy(),
        y=training_target_table[BINARIZED_TARGET_NAME].values
    )

    return model_object


def plot_decision_tree(model_object, predictor_names, num_levels_to_show,
                       font_size=13):
    """Plots single decision tree.

    :param model_object: Trained model created by `setup_classification_tree`.
    :param predictor_names: 1-D list of predictor names.
    :param num_levels_to_show: Number of levels to show in tree.
    :param font_size: Font size.
    """

    _, axes_object = pyplot.subplots(
        1, 1, figsize=(LARGE_FIGURE_WIDTH_INCHES, LARGE_FIGURE_HEIGHT_INCHES)
    )

    _ = plot_tree(
        model_object, max_depth=num_levels_to_show - 1,
        feature_names=predictor_names, label='none', impurity=False,
        rounded=True, precision=2, ax=axes_object, fontsize=font_size
    )


def setup_classification_forest(
        max_predictors_per_split, num_trees=100, min_examples_at_split=30,
        min_examples_at_leaf=30):
    """Sets up (but does not train) random forest for classification.

    :param max_predictors_per_split: Max number of predictors to try at each
        split.
    :param num_trees: Number of trees.
    :param min_examples_at_split: Minimum number of examples at split node.
    :param min_examples_at_leaf: Minimum number of examples at leaf node.
    :return: model_object: Instance of
        `sklearn.ensemble.RandomForestClassifier`.
    """

    return RandomForestClassifier(
        n_estimators=num_trees, min_samples_split=min_examples_at_split,
        min_samples_leaf=min_examples_at_leaf,
        max_features=max_predictors_per_split, bootstrap=True,
        random_state=RANDOM_SEED, verbose=2
    )


def train_classification_forest(model_object, training_predictor_table,
                                training_target_table):
    """Trains random forest for classification.

    :param model_object: Untrained model created by
        `setup_classification_forest`.
    :param training_predictor_table: See doc for `read_tabular_file`.
    :param training_target_table: Same.
    :return: model_object: Trained version of input.
    """

    model_object.fit(
        X=training_predictor_table.to_numpy(),
        y=training_target_table[BINARIZED_TARGET_NAME].values
    )

    return model_object


def setup_classification_gbt(
        max_predictors_per_split, num_trees=100, learning_rate=0.1,
        min_examples_at_split=30, min_examples_at_leaf=30):
    """Sets up (but does not train) gradient-boosted trees for classification.

    :param max_predictors_per_split: Max number of predictors to try at each
        split.
    :param num_trees: Number of trees.
    :param learning_rate: Learning rate.
    :param min_examples_at_split: Minimum number of examples at split node.
    :param min_examples_at_leaf: Minimum number of examples at leaf node.
    :return: model_object: Instance of
        `sklearn.ensemble.GradientBoostingClassifier`.
    """

    return GradientBoostingClassifier(
        loss='exponential', learning_rate=learning_rate, n_estimators=num_trees,
        min_samples_split=min_examples_at_split,
        min_samples_leaf=min_examples_at_leaf,
        max_features=max_predictors_per_split,
        random_state=RANDOM_SEED, verbose=2
    )


def train_classification_gbt(model_object, training_predictor_table,
                             training_target_table):
    """Trains gradient-boosted trees for classification.

    :param model_object: Untrained model created by
        `setup_classification_gbt`.
    :param training_predictor_table: See doc for `read_tabular_file`.
    :param training_target_table: Same.
    :return: model_object: Trained version of input.
    """

    model_object.fit(
        X=training_predictor_table.to_numpy(),
        y=training_target_table[BINARIZED_TARGET_NAME].values
    )

    return model_object


def setup_k_means(num_clusters=10, num_iterations=300):
    """Sets up (but does not train) K-means model.

    :param num_clusters: Number of clusters.
    :param num_iterations: Number of iterations (number of times that clusters
        are updated).
    :return: model_object: Instance of `sklearn.cluster.KMeans`.
    """

    return KMeans(
        n_clusters=num_clusters, init='k-means++', max_iter=num_iterations,
        n_init=1, random_state=RANDOM_SEED, verbose=2
    )


def train_clustering_model(model_object, training_predictor_table):
    """Trains any clustering model.

    :param model_object: Untrained model created by `setup_k_means`,
        `setup_ahc`, or the like.
    :param training_predictor_table: See doc for `read_tabular_file`.
    :return: model_object: Trained version of input.
    """

    model_object.fit(
        X=training_predictor_table.to_numpy()
    )

    return model_object


def use_k_means_for_classifn(
        model_object, training_target_table, new_predictor_table):
    """Uses trained K-means model to classify new examples.

    :param model_object: Trained instance of `sklearn.cluster.KMeans`.
    :param training_target_table: See doc for `read_tabular_file`.
    :param new_predictor_table: Same.
    :return: new_predicted_probs: length-E numpy array of predicted event
        probabilities, where E = number of new examples (number of rows in
        `new_predictor_table`).
    """

    training_classes = training_target_table[BINARIZED_TARGET_NAME].values

    train_example_to_cluster = model_object.labels_
    num_clusters = model_object.cluster_centers_.shape[0]
    cluster_to_training_event_freq = numpy.full(num_clusters, numpy.nan)

    for j in range(num_clusters):
        these_indices = numpy.where(train_example_to_cluster == j)[0]

        # If no training examples in cluster, assume climatology.
        if len(these_indices) == 0:
            cluster_to_training_event_freq[j] = numpy.mean(training_classes)
            continue

        cluster_to_training_event_freq[j] = numpy.mean(
            training_classes[these_indices]
        )

    cluster_index_by_new_example = model_object.predict(
        new_predictor_table.to_numpy()
    )

    return cluster_to_training_event_freq[cluster_index_by_new_example]


def setup_ahc(num_clusters=10):
    """Sets up (but does not train) AHC (agglomerative hierarchical clustering).

    :param num_clusters: Number of clusters.
    :return: model_object: Instance of
        `sklearn.cluster.AgglomerativeClustering`.
    """

    return AgglomerativeClustering(
        n_clusters=num_clusters, affinity='euclidean', linkage='ward',
        distance_threshold=None
    )


def use_ahc_for_classifn(
        model_object, training_predictor_table, training_target_table,
        new_predictor_table):
    """Uses trained AHC model to classify new examples.

    :param model_object: Trained instance of
        `sklearn.cluster.AgglomerativeClustering`.
    :param training_predictor_table: See doc for `read_tabular_file`.
    :param training_target_table: Same.
    :param new_predictor_table: Same.
    :return: new_predicted_target_values: See doc for
        `use_k_means_for_classifn`.
    """

    train_example_to_cluster = model_object.labels_
    training_predictor_matrix = training_predictor_table.to_numpy()
    training_classes = training_target_table[BINARIZED_TARGET_NAME].values

    num_clusters = model_object.n_clusters_
    num_predictors = training_predictor_matrix.shape[1]
    cluster_to_training_event_freq = numpy.full(num_clusters, numpy.nan)
    cluster_centroid_matrix = numpy.full(
        (num_clusters, num_predictors), numpy.nan
    )

    for j in range(num_clusters):
        these_indices = numpy.where(train_example_to_cluster == j)[0]

        if len(these_indices) == 0:
            cluster_centroid_matrix[j, :] = numpy.inf
            continue

        cluster_to_training_event_freq[j] = numpy.mean(
            training_classes[these_indices]
        )
        cluster_centroid_matrix[j, :] = numpy.mean(
            training_predictor_matrix[these_indices], axis=0
        )

    new_predictor_matrix = new_predictor_table.to_numpy()
    distance_matrix = cdist(
        new_predictor_matrix, cluster_centroid_matrix, metric='sqeuclidean'
    )
    cluster_index_by_new_example = numpy.argmin(distance_matrix, axis=1)

    return cluster_to_training_event_freq[cluster_index_by_new_example]


def plot_ahc_dendrogram(training_predictor_table, num_levels_to_show):
    """Plots dendrogram to illustrate agglom hierarchical clustering (AHC).

    :param training_predictor_table: See doc for `read_tabular_file`.
    :param num_levels_to_show: Number of levels to show in dendrogram.
    """

    linkage_matrix = linkage(training_predictor_table.to_numpy(), method='ward')

    _, axes_object = pyplot.subplots(
        1, 1, figsize=(LARGE_FIGURE_WIDTH_INCHES, LARGE_FIGURE_HEIGHT_INCHES)
    )

    dendrogram(
        linkage_matrix, truncate_mode='level', p=num_levels_to_show,
        no_labels=True, ax=axes_object
    )

    axes_object.set_yticks([], [])
    pyplot.show()


def plot_basic_activations():
    """Plots basic activation functions."""

    function_names = [
        SIGMOID_FUNCTION_NAME, TANH_FUNCTION_NAME, RELU_FUNCTION_NAME
    ]
    function_names_verbose = ['Sigmoid', 'tanh', 'ReLU']
    input_values = numpy.linspace(-3, 3, num=1000, dtype=float)

    _, axes_object = pyplot.subplots(
        1, 1, figsize=(FIGURE_WIDTH_INCHES, FIGURE_HEIGHT_INCHES)
    )
    axes_object.plot(
        input_values, numpy.zeros(input_values.shape),
        linewidth=2, linestyle='dashed', color=GREY_COLOUR
    )

    function_colours = [GREEN_COLOUR, ORANGE_COLOUR, PURPLE_COLOUR]

    for i in range(len(function_names)):
        these_output_values = _do_activation(
            input_values=input_values, function_name=function_names[i],
            slope_param=0.
        )
        axes_object.plot(
            input_values, these_output_values, linewidth=4, linestyle='solid',
            color=function_colours[i], label=function_names_verbose[i]
        )

    axes_object.legend(loc='upper left')
    axes_object.set_xlabel('Input (before activation)')
    axes_object.set_ylabel('Output (after activation)')
    pyplot.show()


def plot_fancy_activations():
    """Plots fancy activation functions."""

    function_names = [
        SELU_FUNCTION_NAME, ELU_FUNCTION_NAME, RELU_FUNCTION_NAME
    ]
    function_names_verbose = ['SeLU', 'eLU', 'Leaky ReLU']
    input_values = numpy.linspace(-3, 3, num=1000, dtype=float)

    _, axes_object = pyplot.subplots(
        1, 1, figsize=(FIGURE_WIDTH_INCHES, FIGURE_HEIGHT_INCHES)
    )
    axes_object.plot(
        input_values, numpy.zeros(input_values.shape),
        linewidth=2, linestyle='dashed', color=GREY_COLOUR
    )

    function_colours = [GREEN_COLOUR, ORANGE_COLOUR, PURPLE_COLOUR]

    for i in range(len(function_names)):
        these_output_values = _do_activation(
            input_values=input_values, function_name=function_names[i],
            slope_param=0.2
        )
        axes_object.plot(
            input_values, these_output_values, linewidth=4, linestyle='solid',
            color=function_colours[i], label=function_names_verbose[i]
        )

    axes_object.legend(loc='upper left')
    axes_object.set_xlabel('Input (before activation)')
    axes_object.set_ylabel('Output (after activation)')
    pyplot.show()


def setup_dense_net(
        num_predictors, neuron_counts=DEFAULT_NEURON_COUNTS,
        dropout_rates=DEFAULT_DROPOUT_RATES,
        inner_activ_function_name=DEFAULT_INNER_ACTIV_FUNCTION_NAME,
        inner_activ_function_alpha=DEFAULT_INNER_ACTIV_FUNCTION_ALPHA,
        output_activ_function_name=DEFAULT_OUTPUT_ACTIV_FUNCTION_NAME,
        output_activ_function_alpha=DEFAULT_OUTPUT_ACTIV_FUNCTION_ALPHA,
        l1_weight=DEFAULT_L1_WEIGHT, l2_weight=DEFAULT_L2_WEIGHT,
        use_batch_normalization=True):
    """Sets up (but does not train) dense neural network for binary classifn.

    This method sets up the architecture, loss function, and optimizer.

    D = number of dense layers

    :param num_predictors: Number of input (predictor) variables.
    :param neuron_counts: length-D numpy array with number of neurons for each
        dense layer.  The last value in this array is the number of target
        variables (predictands).
    :param dropout_rates: length-D numpy array with dropout rate for each dense
        layer.  To turn off dropout for a given layer, use NaN or a non-positive
        number.
    :param inner_activ_function_name: Name of activation function for all inner
        (non-output) layers.
    :param inner_activ_function_alpha: Alpha (slope parameter) for
        activation function for all inner layers.  Applies only to ReLU and eLU.
    :param output_activ_function_name: Same as `inner_activ_function_name` but
        for output layer.
    :param output_activ_function_alpha: Same as `inner_activ_function_alpha` but
        for output layer.
    :param l1_weight: Weight for L_1 regularization.
    :param l2_weight: Weight for L_2 regularization.
    :param use_batch_normalization: Boolean flag.  If True, will use batch
        normalization after each inner layer.

    :return: model_object: Untrained instance of `keras.models.Model`.
    """

    # TODO(thunderhoser): Allow for tasks other than binary classification.
    assert neuron_counts[-1] == 1

    input_layer_object = keras.layers.Input(shape=(num_predictors,))
    regularizer_object = _get_weight_regularizer(
        l1_weight=l1_weight, l2_weight=l2_weight
    )

    num_layers = len(neuron_counts)
    layer_object = None

    for i in range(num_layers):
        if layer_object is None:
            this_input_layer_object = input_layer_object
        else:
            this_input_layer_object = layer_object

        layer_object = _get_dense_layer(
            num_output_units=neuron_counts[i],
            weight_regularizer=regularizer_object
        )(this_input_layer_object)

        if i == num_layers - 1:
            layer_object = _get_activation_layer(
                function_name=output_activ_function_name,
                slope_param=output_activ_function_alpha
            )(layer_object)
        else:
            layer_object = _get_activation_layer(
                function_name=inner_activ_function_name,
                slope_param=inner_activ_function_alpha
            )(layer_object)

        if dropout_rates[i] > 0:
            layer_object = _get_dropout_layer(
                dropout_fraction=dropout_rates[i]
            )(layer_object)

        if use_batch_normalization and i != num_layers - 1:
            layer_object = _get_batch_norm_layer()(layer_object)

    model_object = keras.models.Model(
        inputs=input_layer_object, outputs=layer_object
    )

    model_object.compile(
        loss=keras.losses.binary_crossentropy,
        optimizer=keras.optimizers.Adam(),
        metrics=METRIC_FUNCTION_LIST
    )

    model_object.summary()
    return model_object


def train_dense_net(
        model_object, output_dir_name, num_epochs,
        training_predictor_table, training_target_table,
        validation_predictor_table, validation_target_table):
    """Trains dense neural network.

    :param model_object: Untrained network (instance of `keras.models.Model`
        or `keras.models.Sequential`).
    :param output_dir_name: Path to output directory (model and training history
        will be saved here).
    :param num_epochs: Number of training epochs.
    :param training_predictor_table: See doc for `read_tabular_file`.
    :param training_target_table: Same.
    :param validation_predictor_table: Same.
    :param validation_target_table: Same.
    """

    _mkdir_recursive_if_necessary(directory_name=output_dir_name)

    model_file_name = (
        output_dir_name + '/model_epoch={epoch:03d}_val-loss={val_loss:.6f}.h5'
    )

    history_object = keras.callbacks.CSVLogger(
        filename='{0:s}/history.csv'.format(output_dir_name),
        separator=',', append=False
    )
    checkpoint_object = keras.callbacks.ModelCheckpoint(
        filepath=model_file_name, monitor='val_loss', verbose=1,
        save_best_only=True, save_weights_only=False, mode='min', period=1
    )
    early_stopping_object = keras.callbacks.EarlyStopping(
        monitor='val_loss', min_delta=LOSS_PATIENCE,
        patience=EARLY_STOPPING_PATIENCE_EPOCHS, verbose=1, mode='min'
    )
    plateau_object = keras.callbacks.ReduceLROnPlateau(
        monitor='val_loss', factor=PLATEAU_LEARNING_RATE_MULTIPLIER,
        patience=PLATEAU_PATIENCE_EPOCHS, verbose=1, mode='min',
        min_delta=LOSS_PATIENCE, cooldown=PLATEAU_COOLDOWN_EPOCHS
    )

    list_of_callback_objects = [
        history_object, checkpoint_object, early_stopping_object, plateau_object
    ]

    model_object.fit(
        x=training_predictor_table.to_numpy(),
        y=training_target_table[TARGET_NAME].values, batch_size=1024,
        epochs=num_epochs, steps_per_epoch=None, shuffle=True, verbose=1,
        callbacks=list_of_callback_objects,
        validation_data=(
            validation_predictor_table.to_numpy(),
            validation_target_table[TARGET_NAME].values
        ),
        validation_steps=None
    )


def read_dense_net(hdf5_file_name):
    """Reads dense neural network from HDF5 file.

    :param hdf5_file_name: Path to input file.
    :return: model_object: Instance of `keras.models.Model` or
        `keras.models.Sequential`.
    """

    return tf_keras.models.load_model(
        hdf5_file_name, custom_objects=METRIC_FUNCTION_DICT
    )
