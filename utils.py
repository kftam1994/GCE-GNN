import numpy as np
import torch
from torch.utils.data import Dataset
from sklearn.model_selection import train_test_split
from model import trans_to_cuda

def split_validation(train_set, valid_portion):
    train_set_x, train_set_y = train_set
    # n_samples = len(train_set_x)
    # sidx = np.arange(n_samples, dtype='int32')
    # np.random.shuffle(sidx)
    # n_train = int(np.round(n_samples * (1. - valid_portion)))
    # valid_set_x = [train_set_x[s] for s in sidx[n_train:]]
    # valid_set_y = [train_set_y[s] for s in sidx[n_train:]]
    # train_set_x = [train_set_x[s] for s in sidx[:n_train]]
    # train_set_y = [train_set_y[s] for s in sidx[:n_train]]
    
    train_set_x, valid_set_x, train_set_y, valid_set_y = train_test_split(train_set_x, train_set_y, test_size=valid_portion, random_state=42)
    return (train_set_x, train_set_y), (valid_set_x, valid_set_y)

def stack_padding(it,row_length):
    '''
    https://stackoverflow.com/questions/53051560/stacking-numpy-arrays-of-different-length-using-padding
    
    '''
    def resize(row, size):
        new = np.array(row)
        new.resize(size)
        return new
    # reverse the sequence
    mat = np.array( [resize(row[::-1], row_length) for row in it], dtype=np.int32 )

    return mat

def handle_data(inputData, train_len=None):
    len_data = [len(nowData) for nowData in inputData]
    if train_len is None:
        max_len = max(len_data)
    else:
        max_len = train_len
    # reverse the sequence
    # us_pois = [list(reversed(upois)) + [0] * (max_len - le) if le < max_len else list(reversed(upois[-max_len:]))
    #            for upois, le in zip(inputData, len_data)]
    us_pois = stack_padding(inputData,max_len)
    np.testing.assert_array_equal(us_pois,np.asarray([list(reversed(upois)) + [0] * (max_len - le) if le < max_len else list(reversed(upois[-max_len:]))
               for upois, le in zip(inputData, len_data)]))
    # us_msks = [[1] * le + [0] * (max_len - le) if le < max_len else [1] * max_len
    #            for le in len_data]
    us_msks = ~(us_pois == 0)*1
    us_msks = us_msks.astype(np.int8)
    np.testing.assert_array_equal(us_msks,np.asarray([[1] * le + [0] * (max_len - le) if le < max_len else [1] * max_len
               for le in len_data]))
    return us_pois, us_msks, max_len


def handle_adj(adj_dict, n_entity, sample_num, num_dict=None):
    adj_entity = np.zeros([n_entity, sample_num], dtype=np.int64)
    num_entity = np.zeros([n_entity, sample_num], dtype=np.int64)
    for entity in range(1, n_entity):
        neighbor = list(adj_dict[entity])
        neighbor_weight = list(num_dict[entity])
        n_neighbor = len(neighbor)
        if n_neighbor == 0:
            continue
        if n_neighbor >= sample_num:
            sampled_indices = np.random.choice(list(range(n_neighbor)), size=sample_num, replace=False)
        else:
            sampled_indices = np.random.choice(list(range(n_neighbor)), size=sample_num, replace=True)
        adj_entity[entity] = np.array([neighbor[i] for i in sampled_indices])
        num_entity[entity] = np.array([neighbor_weight[i] for i in sampled_indices])

    return adj_entity, num_entity

class ProductData:
    def __init__(self,product_data):
        self.product_features_tensor = trans_to_cuda(torch.Tensor(product_data)) # n_nodes x (1+text embedding size*2), 1 is for normalized price
        
    def get_shape(self):
        return self.product_features_tensor.shape
        
    def get_product_features(self):
        return self.product_features_tensor

class Data(Dataset):
    def __init__(self, data, train_len=None):
        inputs, mask, max_len = handle_data(data[0], train_len)
        # self.inputs = np.asarray(inputs)
        self.inputs = inputs
        self.targets = np.asarray(data[1], dtype=np.int32) # np.asarray(data[1])
        # self.mask = np.asarray(mask)
        self.mask = mask
        self.length = len(data[0])
        self.max_len = max_len

    def __getitem__(self, index):
        u_input, mask, target = self.inputs[index], self.mask[index], self.targets[index]

        max_n_node = self.max_len
        node = np.unique(u_input)
        items = node.tolist() + (max_n_node - len(node)) * [0]
        adj = np.zeros((max_n_node, max_n_node))
        for i in np.arange(len(u_input) - 1):
            u = np.where(node == u_input[i])[0][0]
            adj[u][u] = 1
            if u_input[i + 1] == 0:
                break
            v = np.where(node == u_input[i + 1])[0][0]
            if u == v or adj[u][v] == 4:
                continue
            adj[v][v] = 1
            if adj[v][u] == 2:
                adj[u][v] = 4
                adj[v][u] = 4
            else:
                adj[u][v] = 2
                adj[v][u] = 3

        alias_inputs = [np.where(node == i)[0][0] for i in u_input]

        return [torch.tensor(alias_inputs), torch.tensor(adj), torch.tensor(items),
                torch.tensor(mask), torch.tensor(target), torch.tensor(u_input)]

    def __len__(self):
        return self.length
