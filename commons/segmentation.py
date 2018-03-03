import os
from itertools import count

import cv2
import numpy as np
from PIL import Image as IMG

import preprocess.algorithms.fast_mst as fmst
import preprocess.utils.img_utils as imgutils
import preprocess.utils.filter_utils as fu
from commons.IMAGE import Image
from commons.accumulator import Accumulator
from commons.timer import checktime


class AtureTest:
    def __init__(self, data_dir=None, out_dir=None):

        self.data_dir = data_dir
        self.out_dir = out_dir
        self.writer = None
        self.mask_dir = None
        self.ground_truth_dir = None
        self.fget_mask_file = None
        self.fget_ground_truth_file = None
        self.erode_mask = None
        self.c = count(1)
        if os.path.isdir(self.out_dir) is False:
            os.makedirs(self.out_dir)

    def _segment_now(self, accumulator_2d=None, image_obj=None, params={}):
        image_obj.create_skeleton(threshold=params['sk_threshold'],
                                  kernels=fu.get_chosen_skeleton_filter())
        seed_node_list = fu.get_seed_node_list(image_obj.img_skeleton)

        return fmst.run_segmentation(accumulator_2d=accumulator_2d, image_obj=image_obj, seed_list=seed_node_list,
                                     params=params)

    def _initialize(self, img_obj=None):
        img_obj.working_arr = cv2.bitwise_and(img_obj.working_arr, img_obj.working_arr, mask=img_obj.mask)
        img_obj.apply_bilateral()
        img_obj.apply_gabor(kernel_bank=fu.get_chosen_gabor_bank())
        img_obj.generate_lattice_graph()
        return Accumulator(img_obj=img_obj)

    def _run(self, accumulator=None, params={},
             save_images=False, epoch=0):

        current_segmented = np.zeros_like(accumulator.img_obj.working_arr)
        current_rgb = np.zeros([accumulator.x_size, accumulator.y_size, 3], dtype=np.uint8)

        # Todo implement logic to disable previous connected component in _run() method:
        accumulator.res['graph' + str(epoch)] = self._segment_now(accumulator_2d=current_segmented,
                                                                  image_obj=accumulator.img_obj, params=params)
        current_segmented = cv2.bitwise_and(current_segmented, current_segmented, mask=accumulator.img_obj.mask)
        accumulator.res['segmented' + str(epoch)] = current_segmented

        # save maximum of segmented of all epochs in accumulator to get the correct scores
        accumulator.arr_2d = np.maximum(accumulator.arr_2d, current_segmented)

        accumulator.res['skeleton' + str(epoch)] = accumulator.img_obj.img_skeleton.copy()
        accumulator.res['params' + str(epoch)] = params.copy()
        accumulator.res['scores' + str(epoch)] = imgutils.get_praf1(arr_2d=accumulator.arr_2d,
                                                                    truth=accumulator.img_obj.ground_truth)
        imgutils.rgb_scores(arr_2d=current_segmented, truth=accumulator.img_obj.ground_truth, arr_rgb=current_rgb)
        accumulator.res['segmented_rgb' + str(epoch)] = current_rgb

        imgutils.rgb_scores(arr_2d=accumulator.arr_2d, truth=accumulator.img_obj.ground_truth,
                            arr_rgb=accumulator.arr_rgb)
        self._save(accumulator=accumulator, params=params, epoch=epoch, save_images=save_images)

    def run_for_all_images(self, params_combination=[], save_images=False, epochs=1, alpha_decay=0):

        self.writer = open(self.out_dir + os.sep + "segmentation_result.csv", 'w')
        self.writer.write(
            'ITR,EPOCH,FILE_NAME,FSCORE,PRECISION,RECALL,ACCURACY,'
            'SK_THRESHOLD,'
            'ALPHA,'
            'GABOR_CONTRIB,'
            'SEG_THRESHOLD\n'
        )

        for file_name in os.listdir(self.data_dir):
            img_obj = Image(data_dir=self.data_dir, file_name=file_name)
            # Todo load mask and ground truth
            accumulator = self._initialize(img_obj)
            for params in params_combination:
                for i in range(epochs):
                    print('Running epoch: ' + str(i))
                    if i > 0:
                        self._disable_segmented_vessels(accumulator=accumulator, params=params, alpha_decay=alpha_decay)
                    self._run(accumulator=accumulator, params=params, save_images=save_images, epoch=i)

                # Reset for new parameter combination
                accumulator.arr_2d = np.zeros_like(accumulator.img_obj.working_arr)
                accumulator.arr_rgb = np.zeros([accumulator.x_size, accumulator.y_size, 3], dtype=np.uint8)
                accumulator.img_obj.working_arr = accumulator.res['image0']

        self.writer.close()

    def run_for_one_image(self, image_obj=None, params={}, save_images=False, epochs=1, alpha_decay=0):

        accumulator = self._initialize(image_obj)

        for i in range(epochs):
            print('Running epoch: ' + str(i))

            if i > 0:
                self._disable_segmented_vessels(accumulator=accumulator, params=params, alpha_decay=alpha_decay)

            self._run(accumulator=accumulator, params=params, save_images=save_images, epoch=i)

        return accumulator

    @checktime
    def _disable_segmented_vessels(self, accumulator=None, params=None, alpha_decay=None):
        # todo something with previous accumulator.img_obj.graph to disable the connectivity
        params['alpha'] -= alpha_decay
        params['sk_threshold'] = 100

    def _save(self, accumulator=None, params=None, epoch=None, save_images=False):
        i = next(self.c)
        base = 'scores' + str(epoch)
        line = str(i) + ',' + \
               'EP' + str(epoch) + ',' + \
               str(accumulator.img_obj.file_name) + ',' + \
               str(round(accumulator.res[base]['F1'], 3)) + ',' + \
               str(round(accumulator.res[base]['Precision'], 3)) + ',' + \
               str(round(accumulator.res[base]['Recall'], 3)) + ',' + \
               str(round(accumulator.res[base]['Accuracy'], 3)) + ',' + \
               str(round(params['sk_threshold'], 3)) + ',' + \
               str(round(params['alpha'], 3)) + ',' + \
               str(round(params['gabor_contrib'], 3)) + ',' + \
               str(round(params['seg_threshold'], 3))
        if self.writer is not None:
            self.writer.write(line + '\n')
            self.writer.flush()

        print('Number of params combination tried: ' + str(i))

        if save_images:
            IMG.fromarray(accumulator.arr_rgb).save(
                os.path.join(self.out_dir, accumulator.img_obj.file_name + '_[' + line + ']' + '.JPEG'))
            IMG.fromarray(accumulator.img_obj.img_gabor).save(
                os.path.join(self.out_dir, accumulator.img_obj.file_name + '_[' + line + ']GABOR' + '.JPEG'))
            IMG.fromarray(accumulator.img_obj.working_arr).save(
                os.path.join(self.out_dir, accumulator.img_obj.file_name + '_[' + line + ']ORIG' + '.JPEG'))
