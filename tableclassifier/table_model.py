'''
Table based data configured and trained with Keras.
'''

import keras
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin
from sklearn.pipeline import FeatureUnion, make_pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, MinMaxScaler


class ExtractColumn(BaseEstimator, TransformerMixin):
    '''
    Pick a DataFrame apart by column.
    '''

    def __init__(self, column_or_series_name):
        '''
        Parameters
        ----------
        column_or_series_name : str
            Key into the data frame to extact a column or series.
        '''
        self._column_or_series_name = column_or_series_name

    def fit(self, X, y=None):
        '''
        No specific need to fit.
        '''
        return self

    def transform(self, data_frame):
        '''
        Parameters
        ----------
        data_frame : Pandas DataFrame
        '''
        return data_frame[self._column_or_series_name]

    def __repr__(self):
        '''
        Repr shows the column name for easier debugging.
        '''
        return "ExtractColumn('{0}')".format(self._column_or_series_name)


class PercentageColumn(BaseEstimator, TransformerMixin):
    '''
    Turn a string percentage column in a Pandas DataFrame like 12.5% into numerical values
    like 0.125.
    '''

    def to_float(self, X):
        '''
        Parameters
        ----------
        X : pandas series or numpy array
        '''
        def percent(x):
            '''
            A percentage as a number, or a NaN.
            '''
            if type(x) is str:
                return float(x.replace('%', '')) / 100.0
            elif x:
                return x / 100.0
            else:
                return np.nan

        return np.nan_to_num(np.array(X.map(percent)).reshape(-1, 1)).astype(np.float32)

    def fit(self, X, y=None):
        '''
        No specific need to fit.
        '''
        return self

    def transform(self, X):
        '''
        Transform a column of data into numerical percentage values.

        Parameters
        ----------
        X : pandas series or numpy array
        '''
        return self.to_float(X)


class NumericColumn(BaseEstimator, TransformerMixin):
    '''
    Take a numeric value column and standardize it.
    '''

    def __init__(self):
        '''
        Set up the internal transformation.
        '''
        self._transformer = MinMaxScaler()

    def fit(self, X, y=None):
        '''
        Fit the standardization.
        '''
        as_feature_array = np.array(X).reshape(-1, 1)
        zeroed = np.nan_to_num(as_feature_array)
        self._transformer.fit(zeroed)
        return self

    def transform(self, X):
        '''
        Transform a column of data into numerical percentage values.

        Parameters
        ----------
        X : pandas series or numpy array
        '''
        as_feature_array = np.array(X).reshape(-1, 1)
        zeroed = np.nan_to_num(as_feature_array)
        return self._transformer.transform(zeroed).astype(np.float32)


class CategoricalColumn(BaseEstimator, TransformerMixin):
    '''
    Take a string or key categorical column and transform it
    to one hot encodings.
    '''

    def __init__(self):
        '''
        Set up the internal transformation.
        '''
        self._labeler = LabelEncoder()
        self._encoder = OneHotEncoder()

    def fit(self, X, y=None):
        '''
        Fit the label and encoding
        '''
        handle_none = list(map(str, X))
        encoded = self._labeler.fit_transform(handle_none)
        self._encoder.fit(encoded.reshape(-1, 1))
        return self

    def transform(self, X):
        '''
        Transform a column of data into one hot encodings.

        Parameters
        ----------
        X : pandas series or numpy array
        '''
        handle_none = list(map(str, X))
        encoded = self._labeler.transform(handle_none)
        return self._encoder.transform(encoded.reshape(-1, 1)).todense().astype(np.float32)


class OutputLabelColumn(BaseEstimator, TransformerMixin):
    '''
    Take a string or key categorical column and transform it to integer labels.
    '''

    def __init__(self):
        '''
        Set up the internal transformation.
        '''
        self._labeler = LabelEncoder()

    def fit(self, X, y=None):
        '''
        Fit the label and encoding
        '''
        handle_none = list(map(str, X))
        self._labeler.fit(handle_none)
        return self

    def transform(self, X):
        '''
        Transform a column of data into one hot encodings.

        Parameters
        ----------
        X : pandas series or numpy array
        '''
        handle_none = list(map(str, X))
        return self._labeler.transform(handle_none).astype(np.int32)


class TableModel(BaseEstimator, TransformerMixin):
    '''
    Base TableModel, this deals with:
    * Specifying transformers at the column/series level for input
        (X) and output (Y) features
    * Combining transformed columns into a feature tensor
    * An override point to build a Keras model
    * Loading and Saving trained weights

    This is an in memory model, and will preserve the original DataFrame.

    >>> from tableclassifier import table_model
    >>> import pandas as pd
    >>> data = pd.DataFrame({'a': ['1%', '99%'], 'b': [1, 2], 'c': ['aa', 'bb'], 'd': [True, False]})
    >>> model = table_model.TableModel( \
            transformers={ \
                'a': table_model.PercentageColumn(), \
                'b': table_model.NumericColumn(), \
                'c': table_model.CategoricalColumn(), \
                'd': table_model.CategoricalColumn(), \
            }, \
            output_name='d' \
        )
    >>> X, Y = model.fit_transform(data)
    >>> X
    matrix([[ 0.01      ,  0.        ,  1.        ,  0.        ],
            [ 0.99000001,  1.        ,  0.        ,  1.        ]], dtype=float32)
    >>> Y
    matrix([[ 0.,  1.],
            [ 1.,  0.]], dtype=float32)
    '''

    def __init__(self, transformers={}, output_name=None):
        '''

        Initialize the model with column/series mappings, only those columns
        specified will be used in the model.

        Parameters
        ----------
        transformers : dict
            Mapping from column/series name to scikit learn style transformer
        output_name : str
            Name of a column/series that will be the output
        '''
        self.transformers = transformers.copy()
        self.output_name = output_name

    def fit(self, data_frame, y=None):
        '''
        Fit the column/series model based on the passed Pandas DataFrame.

        Parameters
        ----------
        data_frame : Pandas DataFrame
            Data frame containing both inputs and outputs in columns/series.
        '''
        if not hasattr(self, '_output'):
            transformers = self.transformers.copy()
            try:
                self._output = make_pipeline(
                    ExtractColumn(self.output_name),
                    transformers[self.output_name]
                )
                del transformers[self.output_name]
            except KeyError:
                raise KeyError(
                    '{0} has no transformer'.format(self.output_name))
            # each column is an extraction and then a transformation
            pipelines = [(name, make_pipeline(ExtractColumn(name), transformer))
                         for name, transformer in transformers.items()]
            self._input = FeatureUnion(pipelines)
        self._input.fit(data_frame)
        self._output.fit(data_frame)
        return self

    def transform(self, data_frame):
        '''
        Fit the column/series model based on the passed Pandas DataFrame.

        Parameters
        ----------
        data_frame : Pandas DataFrame
            Data frame containing both inputs and outputs in columns/series.
        '''
        return (
            self._input.transform(data_frame),
            self._output.transform(data_frame)
        )

    @property
    def classes(self):
        '''
        Returns
        -------
        An list of the class labels.
        '''
        return self._output.steps[1][1]._labeler.classes_.tolist()

    @classmethod
    def from_config(cls, config):
        '''
        Build up a table model from a configuration file, as passed in from YAML.
        >>> from tableclassifier import table_model
        >>> table_model.TableModel.from_config({'output': 'a', 'input': {'b': 'numeric', 'c': 'percentage', 'd': 'categorical'}})
        TableModel(output_name='a',
              transformers={'b': NumericColumn(), 'c': PercentageColumn(), 'd': CategoricalColumn()})
        '''
        column_map = {
            'numeric': NumericColumn,
            'percentage': PercentageColumn,
            'categorical': CategoricalColumn
        }
        input_config = {name: column_map[value]() for name, value in config['input'].items()}
        return cls(input_config, config['output'])


class KerasClassifierModel(BaseEstimator, ClassifierMixin):
    '''
    Base class for Keras classification models.
    '''

    def __init__(self, verbose=1, epochs=16, batch_size=512):
        '''
        Parameters
        ----------
        verbose : boolean
            Show more output
        epochs : int
            Train this number of cycles
        batch_size : int
            This number of samples per batch
        '''
        self.verbose = verbose
        self.epochs = epochs
        self.batch_size = batch_size

    def compute_class_weights(self, y):
        '''
        Compute the class weighting dictionary for use with
        imbalanced classes.

        Parameters
        ----------
        y : 1d numpy array
        '''
        labels, counts = np.unique(y, return_counts=True)
        class_weight = {
            label: len(y) / count
            for (label, count) in zip(labels, counts)
        }
        return class_weight

    def predict(self, x, batch_size=32, verbose=0):
        '''
        Generate class predictions for the input samples.
        The input samples are processed batch by batch.
        # Arguments
            x: input data, as a Numpy array or list of Numpy arrays
                (if the model has multiple inputs).
            batch_size: integer.
            verbose: verbosity mode, 0 or 1.
        # Returns
            A numpy array of class predictions.
        '''
        proba = self.model.predict(x, batch_size=batch_size, verbose=verbose)
        if proba.shape[-1] > 1:
            return proba.argmax(axis=-1)
        else:
            return (proba > 0.5).astype('int32')


class KerasLogisticRegressionModel(KerasClassifierModel):
    '''
    Logistic regression implemented with Keras.
    '''

    def fit(self, x, y):
        '''
        Create and fit a logistic regression model

        Parameters
        ----------
        x : 2d numpy array
            0 dimension is batch, 1 dimension features
        y : 1d numpy array
            each entry is a class label
        '''
        class_weight = self.compute_class_weights(y)
        y = keras.utils.to_categorical(y).astype(np.float32)
        model = keras.models.Sequential()
        # logistic regression is a one layer model
        model.add(keras.layers.Dense(
            y.shape[1], activation='sigmoid', input_dim=x.shape[1]))
        model.compile(optimizer='adam', loss='categorical_crossentropy')
        self.model = model
        model.fit(x, y,
                  epochs=self.epochs,
                  batch_size=self.batch_size,
                  verbose=self.verbose,
                  class_weight=class_weight,
                  callbacks=[keras.callbacks.EarlyStopping(monitor='loss', patience=2)])
        return self


class KerasDeepClassifierModel(KerasClassifierModel):
    '''
    A dense, deep, normalized network implemented with Keras.
    '''

    def fit(self, x, y):
        '''
        Create and fit a logistic regression model

        Parameters
        ----------
        x : 2d numpy array
            0 dimension is batch, 1 dimension features
        y : 1d numpy array
            each entry is a class label
        '''
        class_weight = self.compute_class_weights(y)
        y = keras.utils.to_categorical(y).astype(np.float32)
        model = keras.models.Sequential()
        model.add(keras.layers.Dense(
            64, activation='relu', input_dim=x.shape[1]))
        model.add(keras.layers.BatchNormalization())
        model.add(keras.layers.Dense(64, activation='relu'))
        model.add(keras.layers.BatchNormalization())
        model.add(keras.layers.Dense(y.shape[1], activation='softmax'))
        model.compile(optimizer='adam', loss='categorical_crossentropy')
        self.model = model
        model.fit(x, y,
                  epochs=self.epochs,
                  batch_size=self.batch_size,
                  verbose=self.verbose,
                  class_weight=class_weight,
                  callbacks=[keras.callbacks.EarlyStopping(monitor='loss', patience=2)])
        return self


class KerasWideAndDeepClassifierModel(KerasClassifierModel):
    '''
    Logistic regression implemented with Keras.
    '''

    def fit(self, x, y):
        '''
        Create and fit a logistic regression model

        Parameters
        ----------
        x : 2d numpy array
            0 dimension is batch, 1 dimension features
        y : 1d numpy array
            each entry is a class label
        '''
        class_weight = self.compute_class_weights(y)
        y = keras.utils.to_categorical(y).astype(np.float32)

        deep = keras.models.Sequential()
        deep.add(keras.layers.Dense(
            512, activation='relu', input_dim=x.shape[1]))
        deep.add(keras.layers.BatchNormalization())
        deep.add(keras.layers.Dense(512, activation='relu'))
        deep.add(keras.layers.BatchNormalization())
        deep.add(keras.layers.Dense(y.shape[1], activation='sigmoid'))

        wide = keras.models.Sequential()
        wide.add(keras.layers.Dense(
            y.shape[1], activation='sigmoid', input_dim=x.shape[1]))

        input = keras.layers.Input(shape=(x.shape[1],))
        wide = wide(input)
        deep = deep(input)
        wide_deep = keras.layers.Concatenate()([wide, deep])
        output = keras.layers.Dense(
            y.shape[1], activation='softmax')(wide_deep)

        model = keras.models.Model(inputs=[input], outputs=[output])

        model.compile(optimizer='adam', loss='categorical_crossentropy')
        self.model = model
        model.fit(x, y,
                  epochs=self.epochs,
                  batch_size=self.batch_size,
                  verbose=self.verbose,
                  class_weight=class_weight,
                  callbacks=[keras.callbacks.EarlyStopping(monitor='loss', patience=4)])
        return self
