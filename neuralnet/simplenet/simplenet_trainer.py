import numpy as np
import torch
from torch.autograd import Variable
import neuralnet.utils.measurements as mggmt

from neuralnet.torchtrainer import NNTrainer


class SimpleNNTrainer(NNTrainer):
    def __init__(self, model=None, checkpoint_dir=None, checkpoint_file=None, log_to_file=True):
        NNTrainer.__init__(self, model=model, checkpoint_dir=checkpoint_dir, checkpoint_file=checkpoint_file,
                           log_to_file=log_to_file)

    def _evaluate(self, dataloader=None, use_gpu=False, force_checkpoint=False, save_best=False):

        TP, FP, TN, FN = 0, 0, 0, 0
        all_predictions = []
        all_scores = []
        all_labels = []
        all_IDs = []
        all_patchIJs = []
        ##### Segment Mode only to use while testing####
        segment_mode = dataloader.dataset.segment_mode
        for i, data in enumerate(dataloader, 0):
            if segment_mode:
                IDs, IJs, inputs, labels = data
            else:
                inputs, labels = data
            inputs = inputs.cuda() if use_gpu else inputs.cpu()
            labels = labels.cuda() if use_gpu else labels.cpu()

            outputs = self.model(inputs)
            _, predicted = torch.max(outputs, 1)

            # Accumulate scores
            all_scores += outputs.clone().cpu().numpy().tolist()
            all_predictions += predicted.clone().cpu().numpy().tolist()
            all_labels += labels.clone().cpu().numpy().tolist()

            ###### For segment mode only ##########
            if segment_mode:
                all_IDs += IDs.clone().cpu().numpy().tolist()
                all_patchIJs += IJs.clone().cpu().numpy().tolist()
            ##### Segment mode End ###############

            _tp, _fp, _tn, _fn = self.get_score(labels, predicted)

            TP += _tp
            TN += _tn
            FP += _fp
            FN += _fn
            p, r, f1, a = mggmt.get_prf1a(TP, FP, TN, FN)

            self._log(','.join(str(x) for x in [1, 0, i + 1, p, r, f1, a]))
            print('Batch[%d/%d] pre:%.3f rec:%.3f f1:%.3f acc:%.3f' % (
                i + 1, dataloader.__len__(), p, r, f1, a),
                  end='\r')

        print()
        all_IDs = np.array(all_IDs, dtype=np.int)
        all_patchIJs = np.array(all_patchIJs, dtype=np.int)
        all_scores = np.array(all_scores)
        all_predictions = np.array(all_predictions)
        all_labels = np.array(all_labels)
        self._save_if_better(save_best=save_best, force_checkpoint=force_checkpoint, score=f1)

        if segment_mode:
            return all_IDs, all_patchIJs, all_scores, all_predictions, all_labels
        return all_predictions, all_labels
