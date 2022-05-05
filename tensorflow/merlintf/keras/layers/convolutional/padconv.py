import tensorflow as tf
from tensorflow.python.keras import constraints
from tensorflow.python.keras import initializers
from tensorflow.python.keras import regularizers
from tensorflow.python.keras.layers.convolutional import Conv

import numpy as np

import optotf.pad

__all__ = ['PadConv1D',
           'PadConv2D',
           'PadConv3D',
           'PadConvScale2D',
           'PadConvScale3D',
           'PadConvScale2DTranspose',
           'PadConvScale3DTranspose',
           ]

"""
Experimental pad conv class for Variational Networks
Dilations and Stridings are NOT fully supported!
"""

class PadConv(Conv):
    def __init__(self,
            rank,
            filters,
            kernel_size,
            strides=1,
            padding='symmetric',
            data_format=None,
            dilation_rate=1,
            #groups=1,
            use_bias=False,
            kernel_initializer='random_uniform',
            bias_initializer='zeros',
            kernel_regularizer=None,
            bias_regularizer=None,
            activity_regularizer=None,
            kernel_constraint=None,
            bias_constraint=None,
            trainable=True,
            name=None,
            zero_mean=False,
            bound_norm=False,
            pad=True,
            **kwargs):
        super().__init__(
               rank,
               filters,
               kernel_size,
               strides=strides,
               padding="valid",
               data_format=data_format,
               dilation_rate=dilation_rate,
               #groups=groups,
               activation=None,
               use_bias=use_bias,
               kernel_initializer=kernel_initializer,
               bias_initializer=bias_initializer,
               kernel_regularizer=kernel_regularizer,
               bias_regularizer=bias_regularizer,
               activity_regularizer=activity_regularizer,
               kernel_constraint=kernel_constraint,
               bias_constraint=bias_constraint,
               trainable=trainable,
               )

        self.optox_padding = padding
        self.pad = pad
        self.zero_mean = zero_mean
        self.bound_norm = bound_norm

    @property
    def true_kernel(self):
        return self.kernel

    def build(self, input_shape):
        super().build(input_shape)
        # define the weight constraints
        if self.zero_mean or self.bound_norm:
            self.kernel.reduction_dim = tuple([d for d in range(tf.rank(self.kernel))])
            reduction_dim_mean = self.kernel.reduction_dim

            def l2_proj(weight, surface=False):
                tmp = weight
                # reduce the mean
                if self.zero_mean:
                    tmp = tmp - tf.reduce_mean(tmp, reduction_dim_mean, True)
                # normalize by the l2-norm
                if self.bound_norm:
                    norm = tf.math.sqrt(tf.reduce_sum(tmp ** 2, self.kernel.reduction_dim, True))
                    if surface:
                        tmp = tmp / tf.math.maximum(norm, tf.ones_like(norm)*1e-9)
                    else:
                        tmp = tmp / tf.math.maximum(norm, tf.ones_like(norm))
                return tmp

            self.kernel.proj = l2_proj
            self.kernel.assign(l2_proj(self.kernel, True))

    def _compute_optox_padding(self):
        pad = []
        for w in self.true_kernel.shape[:self.rank][::-1]:
            pad += [w//2, w//2]
        return pad

    def call(self, inputs):
        # first pad
        pad = self._compute_optox_padding()
        if self.pad and any(pad):
            inputs = optotf.pad._pad(self.rank, inputs, pad, self.optox_padding)

        outputs = self._convolution_op(inputs, self.true_kernel)

        if self.use_bias:
            outputs = tf.nn.bias_add(outputs, self.bias)

        return outputs

    def _conv_transpose_op(self, x, weight, output_shape):
        if self.rank == 1:
            conv_fun = tf.nn.conv1d_transpose
        elif self.rank == 2:
            conv_fun = tf.nn.conv2d_transpose
        elif self.rank == 3:
            conv_fun = tf.nn.conv3d_transpose
        return conv_fun(x, weight, output_shape, padding='SAME', strides=self.strides, dilations=self.dilation_rate)

    def backward(self, x, output_shape=None):
        pad = self._compute_optox_padding()
        ksz = [w for w in self.true_kernel.shape[:self.rank]]

        # determine the output padding
        if not output_shape is None:
            output_shape = tf.unstack(output_shape)
            output_shape[-1] = tf.shape(self.true_kernel)[-2]
            output_padding = [output_shape[i+1] - ((tf.shape(x)[i+1]-1)*self.strides[i]+1) for i in range(self.rank)]
        else:
            output_shape = [tf.shape(x)[0],] + [1 for i in range(self.rank)] + [tf.shape(self.true_kernel)[-2],]
            output_padding = [0 for i in range(self.rank)]

        # construct output shape
        output_shape = [(tf.shape(x)[i] - 1)*self.strides[i-1] + self.dilation_rate[i-1] * (ksz[i-1] - 1) + output_padding[i-1] + 1 if (i > 0 and i < self.rank + 1) else output_shape[i] for i in range(self.rank + 2) ]
        output_shape = tf.stack(output_shape)
        # zero pad input
        pad_k = [w//2 for w in self.kernel_size]
        tf_pad = [[0,0,],] + \
                 [[pad_k[i] + output_padding[i]//2, pad_k[i] + output_padding[i]//2 + np.mod(output_padding[i],2)] for i in range(self.rank)] + \
                 [[0,0,],]
        x = tf.pad(x, tf_pad)

        # remove bias
        if self.use_bias:
            x = tf.nn.bias_add(x, -1 * self.bias)

        # compute the transpose convolution
        x = self._conv_transpose_op(x, self.true_kernel, output_shape)

        # transpose padding
        if self.pad and any(pad):
            x = optotf.pad._pad_transpose(self.rank, x, pad, self.optox_padding)
        return x

class PadConv1D(PadConv):
    def __init__(self,
               filters,
               kernel_size,
               strides=(1,),
               padding='symmetric',
               data_format=None,
               dilation_rate=(1,),
               #groups=1,
               use_bias=False,
               kernel_initializer='random_uniform',
               bias_initializer='zeros',
               kernel_regularizer=None,
               bias_regularizer=None,
               activity_regularizer=None,
               kernel_constraint=None,
               bias_constraint=None,
               zero_mean=False,
               bound_norm=False,
               pad=True,
               **kwargs):
        super(PadConv1D, self).__init__(
            rank=1,
            filters=filters,
            kernel_size=kernel_size,
            strides=strides,
            padding=padding,
            data_format=data_format,
            dilation_rate=dilation_rate,
            #groups=groups,
            use_bias=use_bias,
            kernel_initializer=initializers.get(kernel_initializer),
            bias_initializer=initializers.get(bias_initializer),
            kernel_regularizer=regularizers.get(kernel_regularizer),
            bias_regularizer=regularizers.get(bias_regularizer),
            activity_regularizer=regularizers.get(activity_regularizer),
            kernel_constraint=constraints.get(kernel_constraint),
            bias_constraint=constraints.get(bias_constraint),
            zero_mean=zero_mean,
            bound_norm=bound_norm,
            pad=pad,
            **kwargs)

class PadConv2D(PadConv):
  def __init__(self,
               filters,
               kernel_size,
               strides=(1, 1),
               padding='symmetric',
               data_format=None,
               dilation_rate=(1, 1),
               #groups=1,
               use_bias=False,
               kernel_initializer='random_uniform',
               bias_initializer='zeros',
               kernel_regularizer=None,
               bias_regularizer=None,
               activity_regularizer=None,
               kernel_constraint=None,
               bias_constraint=None,
               zero_mean=False,
               bound_norm=False,
               pad=True,
               **kwargs):
    super(PadConv2D, self).__init__(
        rank=2,
        filters=filters,
        kernel_size=kernel_size,
        strides=strides,
        padding=padding,
        data_format=data_format,
        dilation_rate=dilation_rate,
        #groups=groups,
        use_bias=use_bias,
        kernel_initializer=initializers.get(kernel_initializer),
        bias_initializer=initializers.get(bias_initializer),
        kernel_regularizer=regularizers.get(kernel_regularizer),
        bias_regularizer=regularizers.get(bias_regularizer),
        activity_regularizer=regularizers.get(activity_regularizer),
        kernel_constraint=constraints.get(kernel_constraint),
        bias_constraint=constraints.get(bias_constraint),
        zero_mean=zero_mean,
        bound_norm=bound_norm,
        pad=pad,
        **kwargs)


class PadConv3D(PadConv):
  def __init__(self,
               filters,
               kernel_size,
               strides=(1, 1, 1),
               padding='symmetric',
               data_format=None,
               dilation_rate=(1, 1, 1),
               #groups=1,
               use_bias=False,
               kernel_initializer='random_uniform',
               bias_initializer='zeros',
               kernel_regularizer=None,
               bias_regularizer=None,
               activity_regularizer=None,
               kernel_constraint=None,
               bias_constraint=None,
               zero_mean=False,
               bound_norm=False,
               pad=True,
               **kwargs):
    super(PadConv3D, self).__init__(
        rank=3,
        filters=filters,
        kernel_size=kernel_size,
        strides=strides,
        padding=padding,
        data_format=data_format,
        dilation_rate=dilation_rate,
        #groups=groups,
        use_bias=use_bias,
        kernel_initializer=initializers.get(kernel_initializer),
        bias_initializer=initializers.get(bias_initializer),
        kernel_regularizer=regularizers.get(kernel_regularizer),
        bias_regularizer=regularizers.get(bias_regularizer),
        activity_regularizer=regularizers.get(activity_regularizer),
        kernel_constraint=constraints.get(kernel_constraint),
        bias_constraint=constraints.get(bias_constraint),
        zero_mean=zero_mean,
        bound_norm=bound_norm,
        pad=pad,
        **kwargs)

class PadConvScale2D(PadConv2D):
    def __init__(self,
                filters,
                kernel_size,
                strides=(2, 2),
                padding='symmetric',
                data_format=None,
                dilation_rate=(1, 1),
                #groups=1,
                use_bias=False,
                kernel_initializer='random_uniform',
                bias_initializer='zeros',
                kernel_regularizer=None,
                bias_regularizer=None,
                activity_regularizer=None,
                kernel_constraint=None,
                bias_constraint=None,
                zero_mean=False,
                bound_norm=False,
                pad=True,
                **kwargs):
        super(PadConvScale2D, self).__init__(
            filters=filters,
            kernel_size=kernel_size,
            strides=strides,
            padding=padding,
            data_format=data_format,
            dilation_rate=dilation_rate,
            #groups=groups,
            use_bias=use_bias,
            kernel_initializer=initializers.get(kernel_initializer),
            bias_initializer=initializers.get(bias_initializer),
            kernel_regularizer=regularizers.get(kernel_regularizer),
            bias_regularizer=regularizers.get(bias_regularizer),
            activity_regularizer=regularizers.get(activity_regularizer),
            kernel_constraint=constraints.get(kernel_constraint),
            bias_constraint=constraints.get(bias_constraint),
            zero_mean=zero_mean,
            bound_norm=bound_norm,
            pad=pad,
            **kwargs)
        # create the convolution kernel
        if self.strides[0] > 1 :
            np_k = np.asarray([1, 4, 6, 4, 1], dtype=np.float32)[:, np.newaxis]
            np_k = np_k @ np_k.T
            np_k /= np_k.sum()
            np_k = np.reshape(np_k, (5, 5, 1, 1))
            self.blur = tf.Variable(initial_value=tf.convert_to_tensor(np_k, dtype=tf.keras.backend.floatx()), trainable=False)
   
    @property
    def true_kernel(self):
        kernel = super().true_kernel
        if self.strides[0] > 1 :
            in_channels = tf.shape(kernel)[-2]
            out_channels = tf.shape(kernel)[-1]
            kernel = tf.reshape(kernel, self.kernel_size + (out_channels*in_channels, 1))
            kernel = tf.transpose(kernel, (2, 0, 1, 3))
            for _ in range(self.strides[0]//2):
                kernel = tf.pad(kernel, [[0,0], [5,5], [5,5], [0,0]], 'CONSTANT')
                kernel = tf.nn.conv2d(kernel, self.blur, padding="SAME", strides=self.strides, dilations=self.dilation_rate)
            kernel = tf.transpose(kernel, (1, 2, 0, 3))
            kernel = tf.reshape(kernel, (self.kernel_size[0]+2*self.strides[0], self.kernel_size[1]+2*self.strides[1], in_channels, out_channels))
        return kernel

class PadConvScale2DTranspose(PadConvScale2D):
    def __init__(self,
                filters,
                kernel_size,
                strides=(2, 2),
                padding='symmetric',
                data_format=None,
                dilation_rate=(1, 1),
               # groups=1,
                use_bias=False,
                kernel_initializer='random_uniform',
                bias_initializer='zeros',
                kernel_regularizer=None,
                bias_regularizer=None,
                activity_regularizer=None,
                kernel_constraint=None,
                bias_constraint=None,
                zero_mean=False,
                bound_norm=False,
                pad=True,
                **kwargs):
        super(PadConvScale2DTranspose, self).__init__(
            filters=filters,
            kernel_size=kernel_size,
            strides=strides,
            padding=padding,
            data_format=data_format,
            dilation_rate=dilation_rate,
          #  groups=groups,
            use_bias=use_bias,
            kernel_initializer=initializers.get(kernel_initializer),
            bias_initializer=initializers.get(bias_initializer),
            kernel_regularizer=regularizers.get(kernel_regularizer),
            bias_regularizer=regularizers.get(bias_regularizer),
            activity_regularizer=regularizers.get(activity_regularizer),
            kernel_constraint=constraints.get(kernel_constraint),
            bias_constraint=constraints.get(bias_constraint),
            zero_mean=zero_mean,
            bound_norm=bound_norm,
            pad=pad,
            **kwargs)

    def build(self, input_shape):
        super().build(input_shape)
        kernel_shape = self.kernel_size + (self.filters, input_shape[-1])
        self.kernel = self.add_weight(
            name='kernel',
            shape=kernel_shape,
            initializer=self.kernel_initializer,
            regularizer=self.kernel_regularizer,
            constraint=self.kernel_constraint,
            trainable=True,
            dtype=tf.keras.backend.floatx())

        if self.use_bias:
            self.bias = self.add_weight(
                name='bias',
                shape=(self.filters,),
                initializer=self.bias_initializer,
                regularizer=self.bias_regularizer,
                constraint=self.bias_constraint,
                trainable=True,
                dtype=tf.keras.backend.floatx())

    def call(self, x, output_shape=None):
        return super().backward(x, output_shape)

    def backward(self, x):
        return super().call(x)
        
class PadConvScale3D(PadConv3D):
    def __init__(self,
                filters,
                kernel_size,
                strides=(1, 2, 2),
                padding='symmetric',
                data_format=None,
                dilation_rate=(1, 1, 1),
          #      groups=1,
                use_bias=False,
                kernel_initializer='random_uniform',
                bias_initializer='zeros',
                kernel_regularizer=None,
                bias_regularizer=None,
                activity_regularizer=None,
                kernel_constraint=None,
                bias_constraint=None,
                zero_mean=False,
                bound_norm=False,
                pad=True,
                **kwargs):
        super(PadConvScale3D, self).__init__(
            filters=filters,
            kernel_size=kernel_size,
            strides=strides,
            padding=padding,
            data_format=data_format,
            dilation_rate=dilation_rate,
         #   groups=groups,
            use_bias=use_bias,
            kernel_initializer=initializers.get(kernel_initializer),
            bias_initializer=initializers.get(bias_initializer),
            kernel_regularizer=regularizers.get(kernel_regularizer),
            bias_regularizer=regularizers.get(bias_regularizer),
            activity_regularizer=regularizers.get(activity_regularizer),
            kernel_constraint=constraints.get(kernel_constraint),
            bias_constraint=constraints.get(bias_constraint),
            zero_mean=zero_mean,
            bound_norm=bound_norm,
            pad=pad,
            **kwargs)
        assert self.strides[0] == 1
        # create the convolution kernel
        if self.strides[1] > 1 :
            np_k = np.asarray([1, 4, 6, 4, 1], dtype=np.float32)[:, np.newaxis]
            np_k = np_k @ np_k.T
            np_k /= np_k.sum()
            np_k = np.reshape(np_k, (1, 5, 5, 1, 1))
            self.blur = tf.Variable(initial_value=tf.convert_to_tensor(np_k, dtype=tf.keras.backend.floatx()), trainable=False)

    @property
    def true_kernel(self):
        kernel = super().true_kernel
        if self.strides[1] > 1 :
            in_channels = tf.shape(kernel)[-2]
            out_channels = tf.shape(kernel)[-1]
            kernel = tf.reshape(kernel, self.kernel_size + (out_channels*in_channels, 1))
            kernel = tf.transpose(kernel,  (3, 0, 1, 2, 4))
            for _ in range(self.strides[1]//2):
                kernel = tf.pad(kernel, [[0,0], [0,0], [5,5], [5,5], [0,0]], 'CONSTANT')
                kernel = tf.nn.conv3d(kernel, self.blur, padding="SAME", strides=(1,) + self.strides + (1,), dilations=(1,) + self.dilation_rate + (1,))
            kernel = tf.transpose(kernel, (1, 2, 3, 0, 4))
            kernel = tf.reshape(kernel, (self.kernel_size[0], 
                                         self.kernel_size[1]+2*self.strides[1],
                                         self.kernel_size[2]+2*self.strides[2],
                                         in_channels, out_channels))
        return kernel

class PadConvScale3DTranspose(PadConvScale3D):
    def __init__(self,
                filters,
                kernel_size,
                strides=(1, 2, 2),
                padding='symmetric',
                data_format=None,
                dilation_rate=(1, 1, 1),
           #     groups=1,
                use_bias=False,
                kernel_initializer='random_uniform',
                bias_initializer='zeros',
                kernel_regularizer=None,
                bias_regularizer=None,
                activity_regularizer=None,
                kernel_constraint=None,
                bias_constraint=None,
                zero_mean=False,
                bound_norm=False,
                pad=True,
                **kwargs):
        super(PadConvScale3DTranspose, self).__init__(
            filters=filters,
            kernel_size=kernel_size,
            strides=strides,
            padding=padding,
            data_format=data_format,
            dilation_rate=dilation_rate,
        #    groups=groups,
            use_bias=use_bias,
            kernel_initializer=initializers.get(kernel_initializer),
            bias_initializer=initializers.get(bias_initializer),
            kernel_regularizer=regularizers.get(kernel_regularizer),
            bias_regularizer=regularizers.get(bias_regularizer),
            activity_regularizer=regularizers.get(activity_regularizer),
            kernel_constraint=constraints.get(kernel_constraint),
            bias_constraint=constraints.get(bias_constraint),
            zero_mean=zero_mean,
            pad=pad,
            **kwargs)

    def build(self, input_shape):
        super().build(input_shape)
        kernel_shape = self.kernel_size + (self.filters, input_shape[-1])
        self.kernel = self.add_weight(
            name='kernel',
            shape=kernel_shape,
            initializer=self.kernel_initializer,
            regularizer=self.kernel_regularizer,
            constraint=self.kernel_constraint,
            trainable=True,
            dtype=tf.keras.backend.floatx())

        if self.use_bias:
            self.bias = self.add_weight(
                name='bias',
                shape=(self.filters,),
                initializer=self.bias_initializer,
                regularizer=self.bias_regularizer,
                constraint=self.bias_constraint,
                trainable=True,
                dtype=tf.keras.backend.floatx())

    def call(self, x, output_shape=None):
        return super().backward(x, output_shape)

    def backward(self, x):
        return super().call(x)
