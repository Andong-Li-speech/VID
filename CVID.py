import os
import h5py
import re
import numpy as np
import tensorflow as tf
import cv2
from tensorflow.python.training import moving_averages
from tensorflow.python.ops import control_flow_ops
import matplotlib.pyplot as plt
from utilities import guided_filter, sample_normal

################ batch normalization setting ################
MOVING_AVERAGE_DECAY = 0.9997
BN_EPSILON = 0.001
BN_DECAY = MOVING_AVERAGE_DECAY
UPDATE_OPS_COLLECTION = 'Derain_update_ops'
DERAIN_VARIABLES = 'Derain_variables'
n_latent = 256
#############################################################
num_feature = 16
KernelSize = 3

os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = "6"
FLAGS = tf.app.flags.FLAGS
tf.app.flags.DEFINE_integer('num_h5_file', 2000,
                            """number of training h5 files.""")
tf.app.flags.DEFINE_integer('num_patches', 500,
                            """number of patches in each h5 file.""")
tf.app.flags.DEFINE_float('learning_rate', 0.001,
                          """learning rate.""")
tf.app.flags.DEFINE_integer('epoch', 3,
                            """epoch.""")
tf.app.flags.DEFINE_float('beta', 1e-4,
                            """epoch.""")
tf.app.flags.DEFINE_float('lamb', 1.,
                            """epoch.""")
tf.app.flags.DEFINE_integer('batch_size', 32,
                            """Batch size.""")
tf.app.flags.DEFINE_integer('num_channels', 3,
                            """Number of the input's channels.""")
tf.app.flags.DEFINE_integer('image_size', 80,
                            """Size of the images.""")
tf.app.flags.DEFINE_integer('label_size', 80,
                            """Size of the labels.""")
tf.app.flags.DEFINE_integer('num_samples', 10,
                            """number of the samples.""")
tf.app.flags.DEFINE_string("data_path", "../fu_h5data/", "The path of h5 files")

tf.app.flags.DEFINE_string("save_model_path", "./cvid_model/", "The path of saving model")


def read_data(file):
    with h5py.File(file, 'r') as hf:
        data = hf.get('data')
        label = hf.get('label')
        label_mask = hf.get('label_2')
        return np.array(data), np.array(label), np.array(label_mask)


def kernel_r_att(images, is_training):
    regularizer = tf.contrib.layers.l2_regularizer(scale=1e-10)
    initializer = tf.contrib.layers.xavier_initializer()
    with tf.variable_scope("input_r_att"):
        conv1 = tf.layers.conv2d(images, filters=16, kernel_size=3, padding='same',
                                 kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias1 = tf.layers.batch_normalization(conv1, training=is_training, name=('bn_1'))
        x0 = tf.nn.relu(bn_bias1)

    with tf.variable_scope("conv_1_r_att"):
        conv2 = tf.layers.conv2d(x0, filters=16, kernel_size=3, padding='same', kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias2 = tf.layers.batch_normalization(conv2, training=is_training, name=('bn_2'))
        h_x1 = tf.nn.relu(bn_bias2)

    with tf.variable_scope("conv_2_r_att"):
        conv3 = tf.layers.conv2d(tf.concat([x0, h_x1], axis=3), filters=16, kernel_size=3, padding='same',
                                 kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias3 = tf.layers.batch_normalization(conv3, training=is_training, name=('bn_3'))

        h_x2 = tf.nn.relu(bn_bias3)

    with tf.variable_scope("conv_3_r_att"):
        conv4 = tf.layers.conv2d(tf.concat([x0, h_x1, h_x2], axis=3), filters=16, kernel_size=3, padding='same',
                                 kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias4 = tf.layers.batch_normalization(conv4, training=is_training, name=('bn_4'))

        h_x3 = tf.nn.relu(bn_bias4)

    with tf.variable_scope("conv_4_r_att"):
        conv5 = tf.layers.conv2d(tf.concat([x0, h_x1, h_x2, h_x3], axis=3), filters=16, kernel_size=3, padding='same',
                                 kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias5 = tf.layers.batch_normalization(conv5, training=is_training, name=('bn_5'))

        h_x4 = tf.nn.relu(bn_bias5)

    with tf.variable_scope("conv_5_r_att"):
        conv6 = tf.layers.conv2d(tf.concat([x0, h_x1, h_x2, h_x3, h_x4], axis=3), filters=16, kernel_size=3,
                                 padding='same', kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias6 = tf.layers.batch_normalization(conv6, training=is_training, name=('bn_6'))

        h_x5 = tf.nn.relu(bn_bias6)

        # layer 26
    with tf.variable_scope('conv_6_r_att'):
        conv6 = tf.layers.conv2d(h_x5, filters=1, kernel_size=3, padding='same', kernel_initializer=initializer,
                                 kernel_regularizer=regularizer, )

        bn_bias6 = tf.layers.batch_normalization(conv6, training=is_training, name=('bn_7'))

        r_att = tf.nn.sigmoid(bn_bias6)

    return r_att


def kernel_g_att(images, is_training):
    regularizer = tf.contrib.layers.l2_regularizer(scale=1e-10)
    initializer = tf.contrib.layers.xavier_initializer()
    with tf.variable_scope("input_g_att"):
        conv1 = tf.layers.conv2d(images, filters=16, kernel_size=3, padding='same',
                                 kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias1 = tf.layers.batch_normalization(conv1, training=is_training, name=('bn_1'))
        x0 = tf.nn.relu(bn_bias1)

    with tf.variable_scope("conv_1_g_att"):
        conv2 = tf.layers.conv2d(x0, filters=16, kernel_size=3, padding='same', kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias2 = tf.layers.batch_normalization(conv2, training=is_training, name=('bn_2'))
        h_x1 = tf.nn.relu(bn_bias2)

    with tf.variable_scope("conv_2_g_att"):
        conv3 = tf.layers.conv2d(tf.concat([x0, h_x1], axis=3), filters=16, kernel_size=3, padding='same',
                                 kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias3 = tf.layers.batch_normalization(conv3, training=is_training, name=('bn_3'))

        h_x2 = tf.nn.relu(bn_bias3)

    with tf.variable_scope("conv_3_g_att"):
        conv4 = tf.layers.conv2d(tf.concat([x0, h_x1, h_x2], axis=3), filters=16, kernel_size=3, padding='same',
                                 kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias4 = tf.layers.batch_normalization(conv4, training=is_training, name=('bn_4'))

        h_x3 = tf.nn.relu(bn_bias4)

    with tf.variable_scope("conv_4_g_att"):
        conv5 = tf.layers.conv2d(tf.concat([x0, h_x1, h_x2, h_x3], axis=3), filters=16, kernel_size=3, padding='same',
                                 kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias5 = tf.layers.batch_normalization(conv5, training=is_training, name=('bn_5'))

        h_x4 = tf.nn.relu(bn_bias5)

    with tf.variable_scope("conv_5_g_att"):
        conv6 = tf.layers.conv2d(tf.concat([x0, h_x1, h_x2, h_x3, h_x4], axis=3), filters=16, kernel_size=3,
                                 padding='same', kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias6 = tf.layers.batch_normalization(conv6, training=is_training, name=('bn_6'))

        h_x5 = tf.nn.relu(bn_bias6)

        # layer 26
    with tf.variable_scope('conv_6_g_att'):
        conv6 = tf.layers.conv2d(h_x5, filters=1, kernel_size=3, padding='same', kernel_initializer=initializer,
                                 kernel_regularizer=regularizer, )

        bn_bias6 = tf.layers.batch_normalization(conv6, training=is_training, name=('bn_7'))

        g_att = tf.nn.sigmoid(bn_bias6)

    return g_att


def kernel_b_att(images, is_training):
    regularizer = tf.contrib.layers.l2_regularizer(scale=1e-10)
    initializer = tf.contrib.layers.xavier_initializer()
    with tf.variable_scope("input_b_att"):
        conv1 = tf.layers.conv2d(images, filters=16, kernel_size=3, padding='same',
                                 kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias1 = tf.layers.batch_normalization(conv1, training=is_training, name=('bn_1'))
        x0 = tf.nn.relu(bn_bias1)

    with tf.variable_scope("conv_1_b_att"):
        conv2 = tf.layers.conv2d(x0, filters=16, kernel_size=3, padding='same', kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias2 = tf.layers.batch_normalization(conv2, training=is_training, name=('bn_2'))
        h_x1 = tf.nn.relu(bn_bias2)

    with tf.variable_scope("conv_2_b_att"):
        conv3 = tf.layers.conv2d(tf.concat([x0, h_x1], axis=3), filters=16, kernel_size=3, padding='same',
                                 kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias3 = tf.layers.batch_normalization(conv3, training=is_training, name=('bn_3'))

        h_x2 = tf.nn.relu(bn_bias3)

    with tf.variable_scope("conv_3_b_att"):
        conv4 = tf.layers.conv2d(tf.concat([x0, h_x1, h_x2], axis=3), filters=16, kernel_size=3, padding='same',
                                 kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias4 = tf.layers.batch_normalization(conv4, training=is_training, name=('bn_4'))

        h_x3 = tf.nn.relu(bn_bias4)

    with tf.variable_scope("conv_4_b_att"):
        conv5 = tf.layers.conv2d(tf.concat([x0, h_x1, h_x2, h_x3], axis=3), filters=16, kernel_size=3, padding='same',
                                 kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias5 = tf.layers.batch_normalization(conv5, training=is_training, name=('bn_5'))

        h_x4 = tf.nn.relu(bn_bias5)

    with tf.variable_scope("conv_5_b_att"):
        conv6 = tf.layers.conv2d(tf.concat([x0, h_x1, h_x2, h_x3, h_x4], axis=3), filters=16, kernel_size=3,
                                 padding='same', kernel_regularizer=regularizer,
                                 kernel_initializer=initializer, )

        bn_bias6 = tf.layers.batch_normalization(conv6, training=is_training, name=('bn_6'))

        h_x5 = tf.nn.relu(bn_bias6)

    with tf.variable_scope('conv_6_b_att'):
        conv6 = tf.layers.conv2d(h_x5, filters=1, kernel_size=3, padding='same', kernel_initializer=initializer,
                                 kernel_regularizer=regularizer, )

        bn_bias6 = tf.layers.batch_normalization(conv6, training=is_training, name=('bn_7'))

        b_att = tf.nn.sigmoid(bn_bias6)

    return b_att


def vae_prior(noise, att, is_training):
    regularizer = tf.contrib.layers.l2_regularizer(scale=1e-10)
    initializer = tf.contrib.layers.xavier_initializer()
    x_concat = tf.concat([noise, att], axis=3)
    with tf.variable_scope("prior", reuse=None):
        #  layer 1
        with tf.variable_scope('layer_1'):
            output = tf.layers.conv2d(x_concat, filters=16, kernel_size=3, padding='same',
                                      kernel_initializer=initializer,
                                      kernel_regularizer=regularizer, name='conv_1')
            output = tf.layers.batch_normalization(output, training=is_training, name='bn_1')
            output_shortcut = tf.nn.leaky_relu(output, name='relu_1')

        #  layers 2 to 25
        for i in range(3):
            with tf.variable_scope('layer_%d' % (i * 2 + 2)):
                output = tf.layers.conv2d(output_shortcut, num_feature, KernelSize, padding='same',
                                          kernel_initializer=initializer,
                                          kernel_regularizer=regularizer, name=('conv_%d' % (i * 2 + 2)))
                output = tf.layers.batch_normalization(output, training=is_training, name=('bn_%d' % (i * 2 + 2)))
                output = tf.nn.leaky_relu(output, name=('relu_%d' % (i * 2 + 2)))

            with tf.variable_scope('layer_%d' % (i * 2 + 3)):
                output = tf.layers.conv2d(output, num_feature, KernelSize, padding='same',
                                          kernel_initializer=initializer,
                                          kernel_regularizer=regularizer, name=('conv_%d' % (i * 2 + 3)))
                output = tf.layers.batch_normalization(output, training=is_training, name=('bn_%d' % (i * 2 + 3)))
                output = tf.nn.leaky_relu(output, name=('relu_%d' % (i * 2 + 3)))

            output_shortcut = tf.add(output_shortcut, output)  # shortcut

        # layer 26
        with tf.variable_scope('layer_fianl'):
            output = tf.layers.conv2d(output_shortcut, 1, KernelSize, padding='same',
                                      kernel_initializer=initializer,
                                      kernel_regularizer=regularizer, name='conv_26')
            output = tf.layers.batch_normalization(output, training=is_training, name='bn_26')

        mn = tf.layers.conv2d(output, filters=1, kernel_size=3, strides=1, padding="SAME", activation=None)
        sd = tf.layers.conv2d(output, filters=1, kernel_size=3, strides=1, padding="SAME", activation=None)

        z = sample_normal(mn, sd, FLAGS.num_samples)
        return z, mn, sd


def vae_encoder(X, noise, att, is_training):
    regularizer = tf.contrib.layers.l2_regularizer(scale=1e-10)
    initializer = tf.contrib.layers.xavier_initializer()
    x_concat = tf.concat([X, noise, att], axis=-1)
    with tf.variable_scope("encoder", reuse=None):
        #  layer 1
        with tf.variable_scope('layer_1'):
            output = tf.layers.conv2d(x_concat, filters=16, kernel_size=3, padding='same',
                                      kernel_initializer=initializer,
                                      kernel_regularizer=regularizer, name='conv_1')
            output = tf.layers.batch_normalization(output, training=is_training, name='bn_1')
            output_shortcut = tf.nn.leaky_relu(output, name='relu_1')

        for i in range(3):
            with tf.variable_scope('layer_%d' % (i * 2 + 2)):
                output = tf.layers.conv2d(output_shortcut, num_feature, KernelSize, padding='same',
                                          kernel_initializer=initializer,
                                          kernel_regularizer=regularizer, name=('conv_%d' % (i * 2 + 2)))
                output = tf.layers.batch_normalization(output, training=is_training, name=('bn_%d' % (i * 2 + 2)))
                output = tf.nn.leaky_relu(output, name=('relu_%d' % (i * 2 + 2)))

            with tf.variable_scope('layer_%d' % (i * 2 + 3)):
                output = tf.layers.conv2d(output, num_feature, KernelSize, padding='same',
                                          kernel_initializer=initializer,
                                          kernel_regularizer=regularizer, name=('conv_%d' % (i * 2 + 3)))
                output = tf.layers.batch_normalization(output, training=is_training, name=('bn_%d' % (i * 2 + 3)))
                output = tf.nn.leaky_relu(output, name=('relu_%d' % (i * 2 + 3)))

            output_shortcut = tf.add(output_shortcut, output)  # shortcut

        with tf.variable_scope('layer_final'):
            output = tf.layers.conv2d(output_shortcut, 1, KernelSize, padding='same',
                                      kernel_initializer=initializer,
                                      kernel_regularizer=regularizer, name='conv_26')
            output = tf.layers.batch_normalization(output, training=is_training, name='bn_26')

        mn = tf.layers.conv2d(output, filters=1, kernel_size=3, strides=1, padding="SAME", activation=None)
        sd = tf.layers.conv2d(output, filters=1, kernel_size=3, strides=1, padding="SAME", activation=None)
        z = sample_normal(mn, sd, FLAGS.num_samples)
        return z, mn, sd


def vae_decoder(z, noise, att, is_training):
    regularizer = tf.contrib.layers.l2_regularizer(scale=1e-10)
    initializer = tf.contrib.layers.xavier_initializer()
    noise = tf.tile(tf.expand_dims(noise, axis=0), [FLAGS.num_samples, 1, 1, 1, 1])
    att = tf.tile(tf.expand_dims(att, axis=0), [FLAGS.num_samples, 1, 1, 1, 1])
    x_concat = tf.concat([z, noise, att], axis=-1)
    output_list = []
    with tf.variable_scope("decoder", reuse=None):
        for n in range(FLAGS.num_samples):
            with tf.variable_scope('layer_1', reuse=tf.AUTO_REUSE):
                output = tf.layers.conv2d_transpose(x_concat[n], filters=16, kernel_size=3, padding='same',
                                                    kernel_initializer=initializer,
                                                    kernel_regularizer=regularizer, name='conv_1')
                output = tf.layers.batch_normalization(output, training=is_training, name='bn_1')
                output_shortcut = tf.nn.relu(output, name='relu_1')

            for i in range(3):
                with tf.variable_scope('layer_%d' % (i * 2 + 2), reuse=tf.AUTO_REUSE):
                    output = tf.layers.conv2d_transpose(output_shortcut, num_feature, KernelSize, padding='same',
                                                        kernel_initializer=initializer,
                                                        kernel_regularizer=regularizer, name=('conv_%d' % (i * 2 + 2)))
                    output = tf.layers.batch_normalization(output, training=is_training, name=('bn_%d' % (i * 2 + 2)))
                    output = tf.nn.relu(output, name=('relu_%d' % (i * 2 + 2)))

                with tf.variable_scope('layer_%d' % (i * 2 + 3), reuse=tf.AUTO_REUSE):
                    output = tf.layers.conv2d_transpose(output, num_feature, KernelSize, padding='same',
                                                        kernel_initializer=initializer,
                                                        kernel_regularizer=regularizer, name=('conv_%d' % (i * 2 + 3)))
                    output = tf.layers.batch_normalization(output, training=is_training, name=('bn_%d' % (i * 2 + 3)))
                    output = tf.nn.leaky_relu(output, name=('relu_%d' % (i * 2 + 3)))

                output_shortcut = tf.add(output_shortcut, output)  # shortcut

            with tf.variable_scope('layer_final', reuse=tf.AUTO_REUSE):
                output = tf.layers.conv2d_transpose(output_shortcut, 1, KernelSize, padding='same',
                                                    kernel_initializer=initializer,
                                                    kernel_regularizer=regularizer, name='conv_26')
                output = tf.layers.batch_normalization(output, training=is_training, name='bn_26')

            img = tf.nn.relu(output + noise[n])
            output_list.append(tf.expand_dims(img, axis=0))
        all_img = tf.concat(output_list, axis=0)
        img = tf.reduce_mean(all_img, axis=0)
        return img, all_img


if __name__ == '__main__':
    if not os.path.exists('single_results/'):
        os.makedirs('single_results/')
    images = tf.placeholder(tf.float32, shape=(None, FLAGS.image_size, FLAGS.image_size, FLAGS.num_channels))  # data
    details = tf.placeholder(tf.float32, shape=(None, FLAGS.image_size, FLAGS.image_size, FLAGS.num_channels))  # label
    labels = tf.placeholder(tf.float32,
                            shape=(None, FLAGS.label_size, FLAGS.label_size, FLAGS.num_channels))  # detail layer
    is_training = tf.placeholder(tf.bool)
    labels_mask = tf.placeholder(tf.float32,
                                 shape=(None, FLAGS.label_size, FLAGS.label_size, FLAGS.num_channels))

    labels_mask_r = labels_mask[:, :, :, :1]
    labels_mask_g = labels_mask[:, :, :, 1:2]
    labels_mask_b = labels_mask[:, :, :, 2:3]

    labels_r = labels[:, :, :, :1]
    labels_g = labels[:, :, :, 1:2]
    labels_b = labels[:, :, :, 2:3]

    images_r = images[:, :, :, :1]
    images_g = images[:, :, :, 1:2]
    images_b = images[:, :, :, 2:3]

    details_r = details[:, :, :, :1]
    details_g = details[:, :, :, 1:2]
    details_b = details[:, :, :, 2:3]

    with tf.variable_scope('r_out'):
        r_att = kernel_r_att(images_r, is_training)  # attention
        r_sample, r_mu, r_var = vae_encoder(labels_r, images_r, r_att, is_training)  # encoder
        pr_sample, pr_mu, pr_var = vae_prior(images_r, r_att, is_training)  # prior network
        r_out, all_r = vae_decoder(r_sample, images_r, r_att, is_training)  # decoder

    with tf.variable_scope('g_out'):
        g_att = kernel_g_att(images_g, is_training)
        g_sample, g_mu, g_var = vae_encoder(labels_g, images_g, g_att, is_training)
        pg_sample, pg_mu, pg_var = vae_prior(images_g, g_att, is_training)
        g_out, all_g = vae_decoder(g_sample, images_g, g_att, is_training)
    with tf.variable_scope('b_out'):
        b_att = kernel_b_att(images_b, is_training)
        b_sample, b_mu, b_var = vae_encoder(labels_b, images_b, b_att, is_training)
        pb_sample, pb_mu, pb_var = vae_prior(images_b, b_att, is_training)
        b_out, all_b = vae_decoder(b_sample, images_b, b_att, is_training)
    with tf.variable_scope('final_out'):
        outputs = tf.concat([r_out, g_out, b_out], axis=-1)

    r_kl_loss = 0.5 * tf.reduce_sum((tf.exp(r_var) + (r_mu - pr_mu) ** 2) / tf.exp(pr_var) - 1. + (pr_var - r_var),
                                    axis=[1, 2, 3])
    g_kl_loss = 0.5 * tf.reduce_sum((tf.exp(g_var) + (g_mu - pg_mu) ** 2) / tf.exp(pg_var) - 1. + (pg_var - g_var),
                                    axis=[1, 2, 3])
    b_kl_loss = 0.5 * tf.reduce_sum((tf.exp(b_var) + (b_mu - pb_mu) ** 2) / tf.exp(pb_var) - 1. + (pb_var - b_var),
                                    axis=[1, 2, 3])

    kl_loss = tf.reduce_mean(r_kl_loss+g_kl_loss+b_kl_loss)
    r_att_loss = tf.reduce_sum(tf.squared_difference(labels_mask_r, r_att), axis=[1, 2, 3])
    g_att_loss = tf.reduce_sum(tf.squared_difference(labels_mask_g, g_att), axis=[1, 2, 3])
    b_att_loss = tf.reduce_sum(tf.squared_difference(labels_mask_b, b_att), axis=[1, 2, 3])
    att_loss = tf.reduce_mean(r_att_loss+g_att_loss+b_att_loss)

    r_recon_loss = tf.reduce_sum(tf.squared_difference(r_out, labels_r), axis=[1, 2, 3])
    g_recon_loss = tf.reduce_sum(tf.squared_difference(g_out, labels_g), axis=[1, 2, 3])
    b_recon_loss = tf.reduce_sum(tf.squared_difference(b_out, labels_b), axis=[1, 2, 3])
    recon_loss = tf.reduce_mean(r_recon_loss+g_recon_loss+b_recon_loss)  # MSE loss
    loss = recon_loss + FLAGS.beta * kl_loss + FLAGS.lamb * att_loss
    lr_ = FLAGS.learning_rate  # learning rate
    lr = tf.placeholder(tf.float32, shape=[])

    update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
    with tf.control_dependencies(update_ops):
        train_op = tf.train.AdamOptimizer(lr).minimize(loss)

    var_list = tf.trainable_variables()
    g_list = tf.global_variables()
    bn_moving_vars = [g for g in g_list if 'moving_mean' in g.name]
    bn_moving_vars += [g for g in g_list if 'moving_variance' in g.name]
    var_list += bn_moving_vars

    saver = tf.train.Saver(max_to_keep=5)

    config = tf.ConfigProto()
    config.gpu_options.per_process_gpu_memory_fraction = 0.8  # GPU setting
    config.gpu_options.allow_growth = True

    data_path = FLAGS.data_path
    save_path = FLAGS.save_model_path
    epoch = int(FLAGS.epoch)

    with tf.Session(config=config) as sess:

        sess.run(tf.global_variables_initializer())

        validation_data_name = "validation.h5"
        validation_data, validation_label, validation_label_mask = read_data(
            data_path + validation_data_name)  # data for validation
        validation_detail = validation_data - guided_filter(validation_data)  # detail layer for validation

        if tf.train.get_checkpoint_state('./cvid_model/'):  # load previous trained models
            ckpt = tf.train.latest_checkpoint('./cvid_model/')

            saver.restore(sess, ckpt)
            ckpt_num = re.findall(r"\d", ckpt)
            if len(ckpt_num) == 2:
                start_point = 10 * int(ckpt_num[0]) + int(ckpt_num[1])
            else:
                start_point = int(ckpt_num[0])
            print("Load success")

        else:  # re-training if no previous trained models
            print("re-training")
            start_point = 0

        for j in range(start_point, epoch):  # the number of epoch

            if j + 1 > 1:  # reduce learning rate
                lr_ = FLAGS.learning_rate * 0.1
            if j + 1 > 2:
                lr_ = FLAGS.learning_rate * 0.01

            Training_Loss = 0.

            for h5_num in range(FLAGS.num_h5_file):  # the number of h5 files
                train_data_name = "train" + str(h5_num + 1) + ".h5"
                train_data, train_label, train_label_mask = read_data(data_path + train_data_name)  # data for training
                detail_data = train_data - guided_filter(train_data)  # detail layer for training

                data_size = int(FLAGS.num_patches / FLAGS.batch_size)  # the number of batch
                train_loss = 0.0
                train_r_loss = 0.0
                train_g_loss = 0.0
                train_b_loss = 0.0
                train_rk_loss = 0.0
                train_gk_loss = 0.0
                train_bk_loss = 0.0
                train_ratt_loss = 0.0
                train_gatt_loss = 0.0
                train_batt_loss = 0.0
                for batch_num in range(data_size):
                    rand_index = np.arange(int(batch_num * FLAGS.batch_size), int((batch_num + 1) * FLAGS.batch_size))
                    batch_data = train_data[rand_index, :, :, :]
                    batch_detail = detail_data[rand_index, :, :, :]
                    batch_label = train_label[rand_index, :, :, :]
                    batch_label_mask = train_label_mask[rand_index, :, :, :]
                    _, lossvalue, rk_loss, gk_loss, bk_loss, r_loss, g_loss, b_loss, ra_loss, ga_loss, ba_loss = sess.run(
                        [train_op, loss, r_kl_loss, g_kl_loss, b_kl_loss, r_recon_loss, g_recon_loss, b_recon_loss,
                         r_att_loss, g_att_loss, b_att_loss],
                        feed_dict={images: batch_data,
                                   labels_mask: batch_label_mask,
                                   labels: batch_label, lr: lr_,
                                   is_training: True})
                    Training_Loss += lossvalue  # training loss
                    train_loss += lossvalue
                    train_r_loss += r_loss
                    train_g_loss += g_loss
                    train_b_loss += b_loss
                    train_rk_loss += rk_loss
                    train_gk_loss += gk_loss
                    train_bk_loss += bk_loss
                    train_ratt_loss += ra_loss
                    train_gatt_loss += ga_loss
                    train_batt_loss += ba_loss
                print('training %d epoch, %d / %d h5 files are finished, learning rate = %.4f, Training_Loss = %.4f' %
                      (j + 1, h5_num + 1, FLAGS.num_h5_file, lr_, train_loss))

                print(
                    'r_loss = %.4f, g_loss = %.4f , b_loss = %.4f, rk_loss = %.4f, gk_loss = %.4f , bk_loss = %.4f, ra_loss = %.4f, ga_loss = %.4f , ba_loss = %.4f' %
                    (train_r_loss.mean(), train_g_loss.mean(), train_b_loss.mean(), train_rk_loss.mean(),
                     train_gk_loss.mean(), train_bk_loss.mean(), train_ratt_loss.mean(),
                     train_gatt_loss.mean(), train_batt_loss.mean()))
                model_name = 'model-epoch'  # save model
                save_path_full = os.path.join(save_path, model_name)
                saver.save(sess, save_path_full, global_step=h5_num)
            Training_Loss /= (data_size * FLAGS.num_h5_file)

            Validation_Loss = sess.run(loss, feed_dict={images: validation_data[0:FLAGS.batch_size, :, :, :],
                                                        labels_mask: validation_label_mask[0:FLAGS.batch_size, :, :, :],
                                                        labels: validation_label[0:FLAGS.batch_size, :, :,
                                                                :], is_training: False})  # validation loss

            print('%d epoch is finished, Training_Loss = %.4f, Validation_Loss = %.4f' % (
                j + 1, Training_Loss, Validation_Loss))
