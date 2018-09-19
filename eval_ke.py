import argparse
import time
import logging

import keras
from keras.utils.np_utils import to_categorical

from common.logger_utils import initialize_logging
from keras_.utils import prepare_ke_context, prepare_model, get_data_rec, backend_agnostic_compile


def parse_args():
    parser = argparse.ArgumentParser(description='Evaluate a model for image classification (Keras)',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--rec-train',
        type=str,
        default='../imgclsmob_data/imagenet/rec/train.rec',
        help='the training data')
    parser.add_argument(
        '--rec-train-idx',
        type=str,
        default='../imgclsmob_data/imagenet/rec/train.idx',
        help='the index of training data')
    parser.add_argument(
        '--rec-val',
        type=str,
        default='../imgclsmob_data/imagenet/rec/val.rec',
        help='the validation data')
    parser.add_argument(
        '--rec-val-idx',
        type=str,
        default='../imgclsmob_data/imagenet/rec/val.idx',
        help='the index of validation data')

    parser.add_argument(
        '--model',
        type=str,
        required=True,
        help='type of model to use. see vision_model for options.')
    parser.add_argument(
        '--use-pretrained',
        action='store_true',
        help='enable using pretrained model from gluon.')
    parser.add_argument(
        '--dtype',
        type=str,
        default='float32',
        help='data type for training. default is float32')
    parser.add_argument(
        '--resume',
        type=str,
        default='',
        help='resume from previously saved parameters if not None')

    parser.add_argument(
        '--num-gpus',
        type=int,
        default=0,
        help='number of gpus to use.')
    parser.add_argument(
        '-j',
        '--num-data-workers',
        dest='num_workers',
        default=4,
        type=int,
        help='number of preprocessing workers')

    parser.add_argument(
        '--batch-size',
        type=int,
        default=512,
        help='training batch size per device (CPU/GPU).')

    parser.add_argument(
        '--save-dir',
        type=str,
        default='',
        help='directory of saved models and log-files')
    parser.add_argument(
        '--logging-file-name',
        type=str,
        default='train.log',
        help='filename of training log')

    parser.add_argument(
        '--log-packages',
        type=str,
        default='keras',
        help='list of python packages for logging')
    parser.add_argument(
        '--log-pip-packages',
        type=str,
        default='keras, keras-mxnet, keras-applications, keras-preprocessing',
        help='list of pip packages for logging')
    args = parser.parse_args()
    return args


def get_data(it,
             batch_size,
             num_classes,
             report_speed=False,
             warm_batches_up_for_reporting=100):
    ctr = 0
    warm_up_done = False
    last_time = None

    # Need to feed data as NumPy arrays to Keras
    def get_arrays(db):
        return db.data[0].asnumpy().transpose((0, 2, 3, 1)),\
               to_categorical(
                   y=db.label[0].asnumpy(),
                   num_classes=num_classes)

    # repeat for as long as training is to proceed, reset iterator if need be
    while True:
        try:
            ctr += 1
            db = it.next()

            # Skip this if samples/second reporting is not desired
            if report_speed:

                # Report only after warm-up is done to prevent downward bias
                if warm_up_done:
                    curr_time = time()
                    elapsed = curr_time - last_time
                    ss = float(batch_size * ctr) / elapsed
                    print(" Batch: %d, Samples per sec: %.2f" % (ctr, ss))

                if ctr > warm_batches_up_for_reporting and not warm_up_done:
                    ctr = 0
                    last_time = time()
                    warm_up_done = True

        except StopIteration as e:
            print("get_data exception due to end of data - resetting iterator")
            it.reset()
            db = it.next()

        finally:
            yield get_arrays(db)


def test(net,
         val_gen,
         val_size,
         batch_size,
         num_gpus,
         calc_weight_count=False,
         extended_log=False):

    backend_agnostic_compile(
        model=net,
        loss='categorical_crossentropy',
        optimizer=keras.optimizers.SGD(
            lr=0.01,
            momentum=0.0,
            decay=0.0,
            nesterov=False),
        metrics=['accuracy'],
        num_gpus=num_gpus)

    #net.summary()
    tic = time.time()
    score = net.evaluate_generator(
        generator=val_gen,
        steps=(val_size // batch_size),
        verbose=True)
    if calc_weight_count:
        weight_count = keras.utils.layer_utils.count_params(net.trainable_weights)
        logging.info('Model: {} trainable parameters'.format(weight_count))
    # if extended_log:
    #     logging.info('Test: err-top1={top1:.4f} ({top1})\terr-top5={top5:.4f} ({top5})'.format(
    #         top1=err_top1_val, top5=err_top5_val))
    # else:
    #     logging.info('Test: err-top1={top1:.4f}\terr-top5={top5:.4f}'.format(
    #         top1=err_top1_val, top5=err_top5_val))
    logging.info('Time cost: {:.4f} sec'.format(
        time.time() - tic))
    logging.info('score: {}'.format(score))
    logging.info('Test score: {}'.format(score[0]))
    logging.info('Test accuracy: {}'.format(score[1]))


def main():
    args = parse_args()

    _, log_file_exist = initialize_logging(
        logging_dir_path=args.save_dir,
        logging_file_name=args.logging_file_name,
        script_args=args,
        log_packages=args.log_packages,
        log_pip_packages=args.log_pip_packages)

    batch_size = prepare_ke_context(
        num_gpus=args.num_gpus,
        batch_size=args.batch_size)

    num_classes = 1000
    net = prepare_model(
        model_name=args.model,
        classes=num_classes,
        use_pretrained=args.use_pretrained,
        pretrained_model_file_path=args.resume.strip())

    train_data, val_data = get_data_rec(
        rec_train=args.rec_train,
        rec_train_idx=args.rec_train_idx,
        rec_val=args.rec_val,
        rec_val_idx=args.rec_val_idx,
        batch_size=batch_size,
        num_workers=args.num_workers)

    # train_gen = get_data(
    #     it=train_data,
    #     batch_size=batch_size,
    #     num_classes=num_classes,
    #     report_speed=True)
    val_gen = get_data(
        it=val_data,
        batch_size=batch_size,
        num_classes=num_classes,
        report_speed=True)
    val_size = 50000

    assert (args.use_pretrained or args.resume.strip())
    test(
        net=net,
        val_gen=val_gen,
        val_size=val_size,
        batch_size=batch_size,
        num_gpus=args.num_gpus,
        calc_weight_count=True,
        extended_log=True)


if __name__ == '__main__':
    main()