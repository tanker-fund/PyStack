'''
	Trains the neural network
'''
import os
import random
random.seed(9999)
import numpy as np
import tensorflow as tf

from Settings.arguments import arguments
from NnTraining.tf_data import create_iterator
from NeuralNetwork.value_nn import ValueNn
from NeuralNetwork.metrics import BasicHuberLoss, masked_huber_loss

class Train(ValueNn):
	def __init__(self, data_dir_list, street):
		'''
		@param: [str,...] :list of paths to directories that contains tf records
		'''
		# set up estimator from ValueNn
		super().__init__(street)
		# resume model if exists
		if os.path.exists(self.model_path):
			print('LOADING PREVIOUS MODEL...')
			self.keras_model = tf.keras.models.load_model( self.model_path,
								   custom_objects = {'loss':BasicHuberLoss(delta=1.0),
													 'masked_huber_loss':masked_huber_loss} )
		else: # compile model
			print('COMPILING MODEL...')
			self.compile_keras_model(self.keras_model)
		# set up read paths for train/valid datasets
		self.tfrecords = [f.path for dirpath in data_dir_list for f in os.scandir(dirpath)]
		print('TFRecords', self.tfrecords)
		# random.shuffle(self.tfrecords)
		self.create_keras_callback()


	def compile_keras_model(self, keras_model):
		''' compiles keras model '''
		loss = BasicHuberLoss(delta=1.0)
		optimizer = tf.keras.optimizers.legacy.Adam(learning_rate=arguments.learning_rate, beta_1=0.9, beta_2=0.999, decay=0.0)
		keras_model.compile(loss=loss, optimizer=optimizer, metrics=[masked_huber_loss])


	def train(self, num_epochs, batch_size, verbose=1, validation_size=0.1, start_epoch=0):
		''' trains model with specified parameters '''
		# get list of train and validation set filenames
		num_valid_files = int(len(self.tfrecords)*validation_size) if validation_size < 1 else validation_size
		train_filenames = self.tfrecords[ :-num_valid_files ]
		random.shuffle(train_filenames)
		valid_filenames = self.tfrecords[ -num_valid_files: ]
		# create tf.data iterators
		train_iterator = create_iterator( filenames=train_filenames, train=True,
										   batch_size=batch_size,
										   x_shape=self.x_shape, y_shape=self.y_shape )
		valid_iterator = create_iterator( filenames=valid_filenames, train=False,
										   batch_size=batch_size,
										   x_shape=self.x_shape, y_shape=self.y_shape )
		# count num of elements in both sets
		num_train_elements = len(train_filenames) * arguments.tfrecords_batch_size
		num_valid_elements = len(valid_filenames) * arguments.tfrecords_batch_size
		# train model
		print('Training model...')
		h = self.keras_model.fit( train_iterator,
								  validation_data = valid_iterator,
								  steps_per_epoch = num_train_elements // batch_size,
								  validation_steps = num_valid_elements // batch_size,
								  epochs = num_epochs, verbose = verbose,
								  callbacks = self.callbacks, initial_epoch = start_epoch )


	def create_keras_callback(self):
		''' returns list of keras callbacks '''
		# imports
		from tensorflow.keras.callbacks import ReduceLROnPlateau, ModelCheckpoint, \
												  LearningRateScheduler, EarlyStopping
		# tensorboard callback
		tb_logdir = os.path.join( self.model_dir_path, 'tensorboard' )
		tb = KerasTensorBoard( log_dir=tb_logdir, histogram_freq=25, write_grads=True )
		# Early stopping callback
		es = EarlyStopping(monitor='val_loss', patience=20, verbose=0, mode='min')
		# Save model callback
		mc = ModelCheckpoint(self.model_path, save_best_only=True, monitor='val_loss', mode='min')
		# Change learning rate
		lrs = LearningRateScheduler( lambda epoch: arguments.learning_rate )
		# Reducting LR callback
		lr = ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=5, verbose=1, min_delta=1e-4, mode='min')
		# set keras callback for training
		self.callbacks = [tb, mc, lrs]



class KerasTensorBoard(tf.keras.callbacks.TensorBoard):
	''' keras callback, that saves training/validation losses to tensorboard '''
	def __init__(self, log_dir, **kwargs):
		# Make the original `TensorBoard` log to a subdirectory 'training'
		training_log_dir = os.path.join(log_dir, 'training')
		super(KerasTensorBoard, self).__init__(training_log_dir, **kwargs)
		# Log the validation metrics to a separate subdirectory
		self.val_log_dir = os.path.join(log_dir, 'validation')

	def set_model(self, model):
		# Setup writer for validation metrics
		self.val_writer = tf.summary.FileWriter(self.val_log_dir)
		super(KerasTensorBoard, self).set_model(model)

	def on_epoch_end(self, epoch, logs=None):
		# Pop the validation logs and handle them separately with
		# `self.val_writer`. Also rename the keys so that they can
		# be plotted on the same figure with the training metrics
		logs = logs or {}
		val_logs = {k.replace('val_', 'epoch_'): v for k, v in logs.items() if k.startswith('val_')}
		for name, value in val_logs.items():
			summary = tf.Summary()
			summary_value = summary.value.add()
			summary_value.simple_value = value.item()
			summary_value.tag = name
			self.val_writer.add_summary(summary, epoch)
		self.val_writer.flush()
		# Pass the remaining logs to `TensorBoard.on_epoch_end`
		logs = {k: v for k, v in logs.items() if not k.startswith('val_')}
		super(KerasTensorBoard, self).on_epoch_end(epoch, logs)

	def on_train_end(self, logs=None):
		super(KerasTensorBoard, self).on_train_end(logs)
		self.val_writer.close()




#
