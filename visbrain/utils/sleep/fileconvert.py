"""Group functions for file managment.

This file contains a bundle of functions that can be used to load several
specific files including *.eeg, *.edf...
"""

import numpy as np
import os
import datetime
from warnings import warn

from ..others import check_downsampling

__all__ = ['load_sleepdataset', 'load_hypno', 'save_hypnoToElan',
           'save_hypnoTotxt']


def load_sleepdataset(path, downsample=None):
    """Load a sleep dataset (elan, edf, brainvision).

    Args:
        path: string
            Filename (with full path) to sleep dataset.

    Kargs:
        downsample: float (def 100.)
            Downsampling frequency

    Return:
        sf: int
            The sampling frequency.

        data: np.ndarray
            The data organised as well (n_channels, n_points)

        chan: list
            The list of channel's names.

        N: int
            Number of samples in the original data

        start_time: time(hh:mm:ss)
            Starting time of the recording

        Example:
            >> > import os
            >> >  # Define path where the file is located
            >> > pathfile = 'mypath/'
            >> > path = os.path.join(pathfile, 'myfile.*')
            >> > sf, data, chan, N, start_time = load_sleepdataset(path, 100.)
    """
    # Test if file exist :
    assert os.path.isfile(path)

    # Extract file extension :
    file, ext = os.path.splitext(path)
    ext = ext.lower()

    # Switch between differents types :
    if ext == '.eeg':
        # ELAN :
        if os.path.isfile(path + '.ent'):
            # Apply an automatic downsampling to 100 Hz
            return elan2array(path, downsample)

        # BRAINVISION :
        elif os.path.isfile(file + '.vhdr'):
            return brainvision2array(path, downsample)

        # None :
        else:
            raise ValueError("No header file found in this directory. You "
                             "should have a *.ent (ELAN) or *.vhdr "
                             "(BRAINVISION)")

    # EDF :
    elif ext == '.edf':
        return edf2array(path, downsample)

    elif ext == '.trc':
        return micromed2array(path, downsample)

    # None :
    else:
        raise ValueError("*" + ext + " files are currently not supported.")


def load_hypno(path, npts):
    """Load hypnogram file.

    Sleep stages in the hypnogram should be scored as follow
    see Iber et al. 2007

    Wake:   0
    N1:     1
    N2:     2
    N3:     3
    REM:    4
    Art:    -1  (optional)

    Args:
        path: string
            Filename (with full path) to hypnogram file.

        npts: int
            Data length.

    Return:
        hypno: np.ndarray
            The hypnogram vector with same length as downsampled data.
    """
    # Test if file exist :
    assert os.path.isfile(path)

    # Extract file extension :
    file, ext = os.path.splitext(path)

    # Try loading file :
    try:
        if ext in ['.hyp', '.txt', '.csv']:
            # ----------- ELAN -----------
            if ext == '.hyp':
                hypno = elan_hyp(path, npts)

            # ----------- TXT / CSV -----------
            elif ext in ['.txt', '.csv']:
                hypno = txt_hyp(path, npts)

            # Complete hypnogram if needed :
            n = len(hypno)
            if n < npts:
                hypno = np.append(hypno, hypno[-1]*np.ones((npts-n,)))
            elif n > npts:
                raise ValueError("The length of the hypnogram \
                                 vector must be" + str(npts) +
                                 " (Currently : " + str(n) + ".")

            return hypno

    except:
        warn("\nAn error ocurred while trying to load the hypnogram. An empty"
             " one will be used instead.")
        return None


def elan_hyp(path, npts):
    """Read Elan hypnogram (hyp).

    Args:
        path: str
            Filename(with full path) to Elan .hyp file

        npts: int
            Data length.

    Return:
        hypno: np.ndarray
            The hypnogram vector with same length as downsampled data.

    """
    hyp = np.genfromtxt(path, delimiter='\n', usecols=[0],
                        dtype=None, skip_header=0)

    hyp = np.char.decode(hyp)

    # Sampling rate of original .eeg file
    # sf = 1 / float(hyp[1].split()[1])

    # Extract hypnogram values
    hypno = np.array(hyp[4:], dtype=np.int)

    # Replace values according to Iber et al 2007
    hypno[hypno == -2] = -1
    hypno[hypno == 4] = 3
    hypno[hypno == 5] = 4

    # Get the repetition number :
    rep = int(np.floor(npts/len(hypno)))

    # Resample to get same number of points as in eeg file
    hypno = np.repeat(hypno, rep)

    return hypno


def txt_hyp(path, npts):
    """Read text files (.txt / .csv) hypnogram.

    Args:
        path: str
            Filename(with full path) to hypnogram(.txt)

        npts: int
            Data length.

    Return:
        hypno: np.ndarray
            The hypnogram vector with same length as downsampled data.

    """
    assert os.path.isfile(path)

    file, ext = os.path.splitext(path)

    header = file + '_description.txt'
    assert os.path.isfile(header)

    # Load header file
    labels = np.genfromtxt(header, dtype=str, delimiter=" ", usecols=0)
    values = np.genfromtxt(header, dtype=int, delimiter=" ", usecols=1)
    desc = {label: row for label, row in zip(labels, values)}

    # Load hypnogram file
    hyp = np.genfromtxt(path, delimiter='\n', usecols=[0],
                        dtype=None, skip_header=0)

    if not np.issubdtype(hyp.dtype, np.integer):
        hyp = np.char.decode(hyp)
        hypno = np.array([s for s in hyp if s.lstrip('-').isdigit()],
                         dtype=int)
    else:
        hypno = hyp.astype(int)

    hypno = swap_hyp_values(hypno, desc)

    # Get the repetition number :
    rep = int(np.floor(npts/len(hypno)))

    # Resample to get same number of points as in eeg file
    hypno = np.repeat(hypno, rep)

    return hypno


def swap_hyp_values(hypno, desc):
    """Swap values in hypnogram vector.

    Sleep stages in the hypnogram should be scored as follow
    see Iber et al. 2007

    Args:
        hypno: np.ndarray
            The hypnogram vector

        description: str
            Path to a .txt file containing labels and values of each sleep
            stage separated by a space

    Return:
    hypno_s: np.ndarray
        Hypnogram with swapped values

        e.g from the DREAM bank EDF database
        Stage   Orig. val    New val
        W       5           0
        N1      3           1
        N2      2           2
        N3      1           3
        REM     0           4
    """
    # Swap values
    hypno_s = -1 * np.ones(shape=(hypno.shape), dtype=int)

    if 'Art' in desc:
        hypno_s[hypno == desc['Art']] = -1

    if 'Nde' in desc:
        hypno_s[hypno == desc['Nde']] = -1

    if 'Mt' in desc:
        hypno_s[hypno == desc['Mt']] = -1

    if 'W' in desc:
        hypno_s[hypno == desc['W']] = 0

    if 'N1' in desc:
        hypno_s[hypno == desc['N1']] = 1

    if 'N2' in desc:
        hypno_s[hypno == desc['N2']] = 2

    if 'N3' in desc:
        hypno_s[hypno == desc['N3']] = 3

    if 'N4' in desc:
        hypno_s[hypno == desc['N4']] = 3

    if 'REM' in desc:
        hypno_s[hypno == desc['REM']] = 4

    return hypno_s


def elan2array(path, downsample=None):
    """Read Elan eeg file into NumPy.

    Elan format specs: http: // elan.lyon.inserm.fr/

    Args:
        path: str
            Filename(with full path) to Elan .eeg file

    Kargs
        downsample: float, optional, (def: None)
            The downsampling frequency.

    Return:
        sf: int
            The sampling frequency.

        data: np.ndarray
            The data organised as well(n_channels, n_points)

        chan: list
            The list of channel's names.

        N: int
            Number of samples in the original data

        start_time: time(hh:mm:ss)
            Starting time of the recording
    """
    header = path + '.ent'

    assert os.path.isfile(path)
    assert os.path.isfile(header)

    # Read .ent file
    ent = np.genfromtxt(header, delimiter='\n', usecols=[0],
                        dtype=None, skip_header=0)

    ent = np.char.decode(ent)

    # eeg file version
    eeg_version = ent[0]

    if eeg_version == 'V2':
        nb_oct = 2
        formread = '>i2'
    elif eeg_version == 'V3':
        nb_oct = 4
        formread = '>i4'

    # Sampling rate
    sf = 1. / float(ent[8])

    # Record starting time
    if ent[4] != "No time":
        rec_time = ent[4]
        hour, minutes, sec = ent[4].split(':')
        start_time = datetime.time(int(hour), int(minutes), int(sec))

        rec_date = ent[3]
        day, month, year = ent[3].split(':')
        start_date = datetime.date(int(year) + 1900, int(month), int(day))
    else:
        start_time = datetime.time(0, 0, 0)
        start_date = datetime.date(1900, 1, 1)

    # Channels
    nb_chan = np.int(ent[9])
    nb_chan = nb_chan

    # Last 2 channels do not contain data
    nb_chan_data = nb_chan - 2
    chan_list = np.arange(0, nb_chan_data)
    chan = ent[10:10 + nb_chan_data]

    # Gain
    Gain = np.zeros(nb_chan)
    offset1 = 9 + 3 * nb_chan
    offset2 = 9 + 4 * nb_chan
    offset3 = 9 + 5 * nb_chan
    offset4 = 9 + 6 * nb_chan

    for i in np.arange(1, nb_chan + 1):

        MinAn = float(ent[offset1 + i])
        MaxAn = float(ent[offset2 + i])
        MinNum = float(ent[offset3 + i])
        MaxNum = float(ent[offset4 + i])

        Gain[i - 1] = (MaxAn - MinAn) / (MaxNum - MinNum)

    # Load memmap
    nb_bytes = os.path.getsize(path)
    nb_samples = int(nb_bytes / (nb_oct * nb_chan))

    m_raw = np.memmap(path, dtype=formread, mode='r',
                      shape=(nb_chan, nb_samples), order={'F'})

    # Get original signal length :
    N = m_raw.shape[1]

    # Get downsample factor :
    if downsample is not None:
        # Check down-sampling :
        downsample = check_downsampling(sf, downsample)
        ds = int(np.round(sf / downsample))
    else:
        ds = 1

    # Multiply by gain :
    data = m_raw[chan_list, ::ds] * \
        Gain[chan_list][..., np.newaxis].astype(np.float32)

    return sf, downsample, data, list(chan), N, start_time


def edf2array(path, downsample=None):
    """Read European Data Format (EDF) file into NumPy.

    Use phypno class for reading EDF files:
        http: // phypno.readthedocs.io / api / phypno.ioeeg.edf.html

    Args:
        path: str
            Filename(with full path) to EDF file

    Kargs:
        downsample: float, optional, (def: None)
            The downsampling frequency.

    Return:
        sf: int
            The sampling frequency.

        data: np.ndarray
            The data organised as well(n_channels, n_points)

        chan: list
            The list of channel's names.

        N: int
            Number of points in the original data

        start_time: time(hh:mm:ss)
            Starting time of the recording
    """
    assert os.path.isfile(path)

    from .edf import Edf

    edf = Edf(path)

    # Return header informations
    _, start_time, sf, chan, n_samples, _ = edf.return_hdr()
    start_time = start_time.time()

    # Keep only data channels (e.g excludes marker chan)
    freqs = np.unique(edf.hdr['n_samples_per_record'])
    sf = freqs.max()

    if len(freqs) != 1:
        bad_chans = np.where(edf.hdr['n_samples_per_record'] < sf)
        chan = np.delete(chan, bad_chans)

    # Load all samples of selected channels
    np.seterr(divide='ignore', invalid='ignore')
    data = edf.return_dat(chan, 0, n_samples)

    # Get original signal length :
    N = data.shape[1]

    # Get downsample factor :
    if downsample is not None:
        # Check down-sampling :
        downsample = check_downsampling(sf, downsample)
        ds = int(np.round(sf / downsample))
    else:
        ds = 1

    return float(sf), downsample, data[:, ::ds], list(chan), N, start_time


def brainvision2array(path, downsample=None):
    """Read BrainVision file.

    Poor man's version of https: // gist.github.com / breuderink / 6266871

    Assumes that data are saved with the following parameters:
        - Data format: Binary
        - Orientation: Multiplexed
        - Format: int16

    Args:
        path: str
            Filename(with full path) to .eeg file

    Kargs:
        downsample: float, optional, (def: None)
            The downsampling frequency.

    Return:
        sf: float
            The sampling frequency.

        data: np.ndarray
            The data organised as well(n_channels, n_points)

        chan: list
            The list of channel's names.

        N: int
            Number of points in the original data

        start_time: time(hh:mm:ss)
            Starting time of the recording

    Example:
        >> > import os
        >> >  # Define path where the file is located
        >> > pathfile = 'mypath/'
        >> > path = os.path.join(pathfile, 'myfile.eeg')
        >> > sf, ds, data, chan, N, start_time = brainvision2array(path)
    """
    import re

    assert os.path.splitext(path)[1] == '.eeg'

    header = os.path.splitext(path)[0] + '.vhdr'
    marker = os.path.splitext(path)[0] + '.vmrk'

    assert os.path.isfile(path)
    assert os.path.isfile(header)

    # Read header
    ent = np.genfromtxt(header, delimiter='\n', usecols=[0],
                        dtype=None, skip_header=0)

    ent = np.char.decode(ent)

    # Check header version
    h_vers = int(re.findall('\d+', ent[0])[0])

    if h_vers == 2:
        n_chan = int(re.findall('\d+', ent[10])[0])
        # n_samples = int(re.findall('\d+', ent[11])[0])
        si = float(re.findall('\d+', ent[14])[0])
        sf = 1 / (si * 0.000001)
        assert "INT_16" in ent[22]

    elif h_vers == 1:
        n_chan = int(re.findall('\d+', ent[9])[0])
        si = float(re.findall('\d+', ent[11])[0])
        sf = 1 / (si * 0.000001)
        assert "INT_16" in ent[13]

    # Read marker file (if present) to extract recording time
    if os.path.isfile(marker):
        vmrk = np.genfromtxt(marker, delimiter='\n', usecols=[0],
                             dtype=None, skip_header=0)

        vmrk = np.char.decode(vmrk)
        line_time = np.array(np.where(np.char.find(vmrk, 'Mk1=') == 0)).min()

        st = re.split('\W+', vmrk[line_time])[-1]
        start_date = datetime.date(int(st[0:4]), int(st[4:6]), int(st[6:8]))
        start_time = datetime.time(int(st[8:10]), int(st[10:12]), \
                                                                int(st[12:14]))
    else:
        start_date = datetime.date(1900, 1, 1)
        start_time = datetime.time(0, 0, 0)

    # Extract channel labels and resolution
    start_label = np.array(np.where(np.char.find(ent, 'Ch1=') == 0)).min()

    chan = {}
    resolution = np.empty(shape=n_chan)

    for i, j in enumerate(range(start_label, start_label + n_chan)):
        chan[i] = re.split('\W+', ent[j])[1]
        resolution[i] = float(ent[j].split(",")[2])

    chan = np.array(list(chan.values())).flatten()

    # Check binary format
    assert "MULTIPLEXED" in ent[8]
    assert "BINARY" in ent[6]

    with open(path, 'rb') as f:
        raw = f.read()
        size = int(len(raw) / 2)
        ints = np.ndarray((n_chan, int(size / n_chan)),
                          dtype='<i2', order='F', buffer=raw)

        data = np.float32(np.diag(resolution)).dot(ints)

    # Get original signal length :
    N = data.shape[1]

    # Get downsample factor :
    if downsample is not None:
        # Check down-sampling :
        downsample = check_downsampling(sf, downsample)
        ds = int(np.round(sf / downsample))
    else:
        ds = 1

    return sf, downsample, data[:, ::ds], list(chan), N, start_time


def micromed2array(path, downsample=None):
    """Read Micromed (*.trc) file version 4.

    Poor man's version of micromedio.py from Neo package
    (https://pythonhosted.org/neo/)

    Args:
        path: str
            Filename(with full path) to .trc file

    Kargs:
        downsample: float, optional, (def: None)
            The downsampling frequency.

    Return:
        sf: float
            The sampling frequency.

        downsample: float
            The downsampling frequency

        data: np.ndarray
            The data organised as well(n_channels, n_points)

        chan: list
            The list of channel's names.

        N: int
            Number of samples in the original signal

        start_time: time(hh:mm:ss)
            Starting time of the recording
    """
    import struct

    def read_f(f, fmt):
        return struct.unpack(fmt, f.read(struct.calcsize(fmt)))

    with open(path, 'rb') as f:
        # Read header
        f.seek(175, 0)
        header_version, = read_f(f, 'b')
        assert header_version == 4

        f.seek(138, 0)
        data_start_offset, n_chan, _, sf, nbytes = read_f(f, 'IHHHH')

        f.seek(128, 0)
        day, month, year, hour, minute, sec = read_f(f, 'bbbbbb')
        start_date = datetime.date(year + 1900, month, day)
        start_time = datetime.time(hour, minute, sec)

        # Raw data
        f.seek(data_start_offset, 0)
        m_raw = np.fromstring(f.read(), dtype='u'+str(nbytes))
        m_raw = m_raw.reshape((int(m_raw.size/n_chan), n_chan)).transpose()

        # Read label / gain
        gain = []
        chan = []
        logical_ground = []
        data = np.empty(shape=m_raw.shape, dtype=np.float32)

        f.seek(176, 0)
        zone_names = ['ORDER', 'LABCOD']
        zones = {}
        for zname in zone_names:
            zname2, pos, length = read_f(f, '8sII')
            zones[zname] = zname2, pos, length

        zname2, pos, length = zones['ORDER']
        f.seek(pos, 0)
        code = np.fromfile(f, dtype='u2', count=n_chan)

        for c in range(n_chan):
            zname2, pos, length = zones['LABCOD']
            f.seek(pos + code[c] * 128 + 2, 0)

            chan = np.append(chan, f.read(6).decode('utf-8').strip())
            ground = f.read(6).decode('utf-8').strip()
            logical_min, logical_max, logic_ground_chan, physical_min, \
                                physical_max = read_f(f, 'iiiii')

            logical_ground = np.append(logical_ground, logic_ground_chan)

            gain = np.append(gain, float(physical_max - physical_min) / \
                                        float(logical_max-logical_min+1))

    # Multiply by gain
    m_raw = m_raw - logical_ground[:, np.newaxis]
    data = m_raw * gain[:, np.newaxis].astype(np.float32)

    # Get original signal length :
    N = data.shape[1]

    # Get downsample factor :
    if downsample is not None:
        # Check down-sampling :
        downsample = check_downsampling(sf, downsample)
        ds = int(np.round(sf / downsample))
    else:
        ds = 1

    return sf, downsample, data[:, ::ds], list(chan), N, start_time


def save_hypnoToElan(filename, hypno, sf, sfori, N):
        """Save hypnogram in Elan file format (*.hyp).

        Args:
            filename: str
                Filename (with full path) of the file to save

            hypno: np.ndarray
                Hypnogram array, same length as data

            sf: int
                Sampling frequency of the data (after downsampling)

            sfori: int
                Original sampling rate of the raw data

            N: int
                Original number of points in the raw data
        """
        # Check data format
        sf = int(sf)
        hypno = hypno.astype(int)
        hypno[hypno == 4] = 5
        step = int(hypno.shape / np.round(N / sfori))

        hdr = np.array([['time_base 1.000000'],
                        ['sampling_period ' + str(np.round(1/sfori, 8))],
                        ['epoch_nb ' + str(int(N / sfori))],
                        ['epoch_list']]).flatten()

        # Save
        export = np.append(hdr, hypno[::step].astype(str))
        np.savetxt(filename, export, fmt='%s')


def save_hypnoTotxt(filename, hypno, sf, sfori, N, window=1.):
        """Save hypnogram in txt file format (*.txt).

        Header is in file filename_description.txt

        Args:
            filename: str
                Filename (with full path) of the file to save

            hypno: np.ndarray
                Hypnogram array, same length as data

            sf: float
                Sampling frequency of the data (after downsampling)

            sfori: int
                Original sampling rate of the raw data

            N: int
                Original number of points in the raw data

        Kargs:
            window: float, optional, (def 1)
                Time window (second) of each point in the hypno
                Default is one value per second
                (e.g. window = 30 = 1 value per 30 second)
        """
        base = os.path.basename(filename)
        dirname = os.path.dirname(filename)
        descript = os.path.join(dirname,
                                os.path.splitext(base)[0] + '_description.txt')

        # Save hypno
        step = int(hypno.shape / np.round(N / sfori))
        np.savetxt(filename, hypno[::step].astype(int), fmt='%s')

        # Save header file
        hdr = np.array([['time ' + str(window)], ['W 0'], ['N1 1'], ['N2 2'],
                        ['N3 3'], ['REM 4'], ['Art -1']]).flatten()
        np.savetxt(descript, hdr, fmt='%s')
