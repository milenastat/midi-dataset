'''
Given alignment results, create a dataset for hashing using those alignments
which were sucessful (based on simple thresholding of dynamic programming
score) consisting of aligned CQTs from audio and synthesized MIDI
'''

import sys
sys.path.append('..')
import numpy as np
import os
import pretty_midi
import joblib
import feature_extraction
import deepdish
import traceback

# A DP score below this means the alignment is bad
SCORE_THRESHOLD = .5
RESULTS_PATH = '../results'


def process_one_file(diagnostics_file, output_filename):
    # If the alignment failed and there was no diagnostics file, return
    if not os.path.exists(diagnostics_file):
        return
    diagnostics = deepdish.io.load(diagnostics_file)
    score = diagnostics['score']
    # Skip bad alignments
    if score < SCORE_THRESHOLD:
        return
    try:
        # Load in MIDI data
        pm = pretty_midi.PrettyMIDI(str(diagnostics['output_midi_filename']))
        # Synthesize MIDI data and extract CQT
        midi_gram = feature_extraction.midi_cqt(pm)
        midi_frame_times = feature_extraction.frame_times(midi_gram)
        # Get audio CQT
        audio_features = deepdish.io.load(
            str(diagnostics['audio_features_filename']))
        audio_gram = audio_features['gram']
        audio_frame_times = feature_extraction.frame_times(audio_gram)
        # Get indices which fall within the range of correct alignment
        start_time = min([n.start for i in pm.instruments for n in i.notes])
        end_time = min(pm.get_end_time(), midi_frame_times.max(),
                       audio_frame_times.max())
        if end_time <= start_time:
            return
        # Mask out the times within the aligned region
        audio_gram = audio_gram[np.logical_and(audio_frame_times >= start_time,
                                               audio_frame_times <= end_time)]
        midi_gram = midi_gram[np.logical_and(midi_frame_times >= start_time,
                                             midi_frame_times <= end_time)]
        # Write out matrices with a newaxis at front (for # of channels)
        # Also downcast to float32, to save space and for GPU-ability
        deepdish.io.save(
            output_filename, {'X': midi_gram[np.newaxis].astype(np.float32),
                              'Y': audio_gram[np.newaxis].astype(np.float32)})
    except Exception as e:
        print "Error for {}: {}".format(
            diagnostics_file, traceback.format_exc(e))
        return


def pair_to_path(pair):
    '''
    Convert a pair [midi_md5, dataset, id] to a diagnostics files path

    Parameters
    ----------
    pair : list of str
        Three entry list of [midi_md5, dataset, id]

    Returns
    -------
    path : str
        Path to the diagnostics file
    '''
    midi_md5, dataset, id = pair
    return '{}_{}_{}.h5'.format(dataset, id, midi_md5)

if __name__ == '__main__':

    aligned_path = os.path.join(RESULTS_PATH, 'clean_midi_aligned', 'h5')

    for dataset in ['train', 'valid']:
        # Create output path for this dataset split
        output_path = os.path.join(
            RESULTS_PATH, 'training_dataset', dataset, 'h5')
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        # Load in all pairs for this split
        pair_file = os.path.join(
            RESULTS_PATH, '{}_pairs.csv'.format(dataset))
        with open(pair_file) as f:
            pairs = [[line.strip().split(',')[n] for n in [1, 2, 0]]
                     for line in f]
        # Create hashing .h5 file for each pair
        joblib.Parallel(n_jobs=10, verbose=51)(
            joblib.delayed(process_one_file)(
                os.path.join(aligned_path, '{}_{}_{}.h5'.format(*pair)),
                os.path.join(output_path, '{}_{}_{}.h5'.format(*pair)))
            for pair in pairs)
