import os
import numpy as np
from evaluation import calculate_eval_metrics
import fasttext


class ClassifySentences(object):
    """Train (training set), evaluate (test set), and use (predict set)
    a Fasttext model that classifies individual radiology report sentences as
    'sick' or 'healthy'.
    
    The final results are stored in the dataframes train_data, test_data,
    and predict_data."""
    def __init__(self, train_data, test_data, predict_data,
                 results_dir, save_model_files=False):
        """Variables:
        <results_dir>: path to directory in which results will be saved
        <save_model_files>: bool. If True, save the model files."""
        self.train_data = train_data
        self.test_data = test_data
        self.predict_data = predict_data
        
        # For the classifier, train and test data are required
        assert not self.train_data.empty, 'Training data set needs to be defined when using sarle hybrid'
        assert not self.test_data.empty, 'Test data set needs to be defined when using sarle hybrid, to evaluate the model'
        
        self.results_dir = results_dir
        self.save_model_files = save_model_files
        print('Running sentence_classifier')
        
    def run_all(self):
        self._prepare_data()
        self._run_fasttext_model()
    
    def _prepare_data(self):
        """Save the fasttext input files to disk and save the corresponding
        filename order as self.data_set_filename_order"""
        self._save_fasttext_split('train',self.train_data)
        self._save_fasttext_split('test',self.test_data)
    
    def _save_fasttext_split(self, setname, data):
        """Create the file fasttext_<name>_set.txt in <self.results_dir>
        for the data set specified by <setname>, containing the sentence and
        label data formatted for fasttext: the file has no header, and each line
        contains a label (either '__label__s' or '__label__h') followed by a
        sentence."""
        assert setname in ['train','test','predict']
        data_set = []
        for index in data.index.values.tolist():
            sentence = data.at[index,'Sentence']
            label = '__label__'+data.at[index,'Label']
            data_set.append([label,sentence])
        np.savetxt(os.path.join(self.results_dir,'fasttext_'+setname+'_set.txt'), np.array(data_set), fmt='%s')
    
    def _run_fasttext_model(self):
        """Use the prepared train and test data to run the fasttext model"""
        model = fasttext.train_unsupervised(os.path.join(self.results_dir,'fasttext_train_set.txt'), model='skipgram')
        model.save_model(os.path.join(self.results_dir,'skipgram_model.bin'))
        self.classifier = fasttext.train_supervised(os.path.join(self.results_dir, 'fasttext_train_set.txt'))
        self.classifier.save_model(os.path.join(self.results_dir,'classifier.bin'))
        result = self.classifier.test(os.path.join(self.results_dir, 'fasttext_test_set.txt'))
        #result is a tuple (N, precision, recall)
        print('(N, P@1, R@1)=',result)
        self.train_data = self._get_preds_and_perf('train',self.train_data)
        self.test_data = self._get_preds_and_perf('test',self.test_data)
        if not self.predict_data.empty:
            self.predict_data = self._get_preds_and_perf('predict',self.predict_data)
        self._clean_up()
        
       
    
    def _get_preds_and_perf(self, setname, data):
        """Report overall performance and save binary labels, predicted
        labels, and predicted probabilities in <data>"""
        # Make predictions
        print('*** '+setname+' ***')
        data = self._extract_predictions(data)
        
        # Report performance
        if setname != 'predict':
            accuracy, auc, average_precision = calculate_eval_metrics(predicted_labels=data['PredLabel'].values.tolist(), predicted_probs=data['PredProb'].values.tolist(), true_labels=data['BinLabel'].values.tolist())
            print('Accuracy:',accuracy)
            print('AUC:',auc)
            print('Average Precision:',average_precision)
        return data
        
    def _extract_predictions(self, data):
        """Return <data> with the predicted labels and probabilities added"""
        sentences = data['Sentence'].values.tolist()
        preds_h_or_s = self.classifier.predict(sentences)
        predicted_labels = [x[0].replace('__label__','') for x in preds_h_or_s[0]]
        predicted_probs = [x[0] for x in preds_h_or_s[1]]
        
        # Now flip the predicted probs for the healthy because we want to
        # output the probability that the sentence is sick.
        # Also binarize the predicted labels to 1 and 0 from s and h
        predicted_labels_final = []
        predicted_probs_final = []
        for index in range(len(sentences)):
            if predicted_labels[index] == 's':
                predicted_labels_final.append(1)
                predicted_probs_final.append(predicted_probs[index])
            elif predicted_labels[index] == 'h':
                predicted_labels_final.append(0)
                # One minus, because we want this to report the probability of being
                # sick (which is the opposite of the probability of being healthy)
                predicted_probs_final.append(1 - predicted_probs[index])
            else:
                assert False
        data['PredLabel'] = predicted_labels_final
        data['PredProb'] = predicted_probs_final
        return data
    
    def _clean_up(self):
        if not self.save_model_files:
            os.remove(os.path.join(self.results_dir,'skipgram_model.bin'))
            os.remove(os.path.join(self.results_dir,'classifier.bin'))
            os.remove(os.path.join(self.results_dir,'fasttext_train_set.txt'))
            os.remove(os.path.join(self.results_dir,'fasttext_test_set.txt'))                  