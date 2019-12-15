import math 
import torch
import torch.nn.functional as F
from torch.autograd import Variable
import numpy as np
from math import exp
from tqdm import tqdm


def _saveCurrentGradient(grad):
    global currentGradient
    currentGradient = grad


def get_probabilites(vec):
    probabilities = F.softmax(vec,dim=1)
    return probabilities


def _getPrediction(layer,sample):
    pred = layer.forward(sample)
    if pred.data[0][0] > pred.data[0][1]:
        return 0
    else:
        return 1


def findPerturbationToFlipPredict(sample,layer,classifier_length,attributes,attribute_length,class_to_reach):
    max_iterations = 100
    ##to not alter original starting sample
    sample_copy = torch.unsqueeze(sample.clone(),0)
    sample_copy.register_hook(_saveCurrentGradient)
    if class_to_reach == 1:
        desidered_labels = Variable(torch.cuda.FloatTensor([[0,1]]))
    else:
        desidered_labels = Variable(torch.cuda.FloatTensor([[1,0]]))
    xi = sample_copy
    sum_ri = Variable(torch.cuda.FloatTensor(classifier_length).fill_(0))
    iterations = 1
    continue_search = True
    while(continue_search and iterations <max_iterations and _getPrediction(layer,xi)!=class_to_reach):      
        output = layer.forward(xi)
        probabilities = get_probabilites(output)
        ##f(x) is the probability of the current state
        if class_to_reach == 1:
            fx = 1 - probabilities[0][1]
        else:
            fx = probabilities[0][1]
        #- to move to the opposite direction of gradients
        loss = F.binary_cross_entropy(F.softmax(output,dim=1),desidered_labels)
        loss.backward()
        current_gradient = currentGradient
        partial_derivative = Variable(torch.cuda.FloatTensor(classifier_length).fill_(0))
        for att in attributes:
            start_index = att * attribute_length
            end_index = start_index+ attribute_length
            partial_derivative[start_index:end_index] = current_gradient[:,start_index:end_index]
        current_norm = torch.norm(partial_derivative)
        if current_norm.data[0] <=0.00001:
            sum_ri = Variable(torch.cuda.FloatTensor(classifier_length).fill_(0))
            print(" Gradient is null")
            continue_search = False
        else:
            ri = -(fx/current_norm)*(partial_derivative)
            xi = Variable(xi.data+ri.data,requires_grad=True)
            sum_ri += ri
            iterations +=1
    if iterations>=max_iterations:
        sum_ri = Variable(torch.cuda.FloatTensor(classifier_length).fill_(0))
        print("can't converge in {} iterations".format(str(iterations)))
        
    return sum_ri


def findCloserNaif(v,opposite_data,opposite_data_label,model,attribute_idx,attribute_len):
    start_idx = attribute_idx*attribute_len
    end_idx = start_idx+attribute_len
    original_prediction = model.forward(torch.unsqueeze(v,0))
    if original_prediction.data[0][0] > original_prediction.data[0][1]:
        original_label = 0
    else:
        original_label = 1
    original_att_value = v[start_idx:end_idx].clone()
    distances = []
    perturbations = []
    for batch in opposite_data:
        len_batch = len(batch)
        v_batch = torch.unsqueeze(v,0).clone()
        v_batch_var = Variable(v_batch.data.repeat(len_batch,1))
        batch_copy = batch.clone()
        v_batch_var[:,start_idx:end_idx] = batch_copy[:,start_idx:end_idx]
        predictions = model.forward(v_batch_var)
        i = 0
        for pred in predictions:
            if (opposite_data_label ==1 and pred.data[1]>pred.data[0])or (opposite_data_label ==0 and pred.data[0] >pred.data[1]):
                ri = batch[i][start_idx:end_idx]-original_att_value
                distances.append(torch.norm(ri).data[0])
                perturbations.append(batch[i][start_idx:end_idx])
            i +=1
    if len(distances) >0 and original_label != opposite_data_label:
        closer_distance = min(distances)
        best_idx = distances.index(closer_distance)
        return (perturbations[best_idx])
    else:
        ##If we return 0 vector it means that we couldn't find any perturbation
        return Variable(torch.zeros(attribute_len))
    

def computeRi(layer,attributes,dataset,attribute_length,class_to_reach):
    #each column of this matrix is related to a specific attribute
    layer_len = len(attributes)*attribute_length
    ri = []
    for batch in dataset:
        for sample in tqdm(batch):
            current_sample_ris = list(map(lambda att: findPerturbationToFlipPredict(sample,layer,layer_len,[attributes.index(att)],
                                                                                           attribute_length,class_to_reach),attributes))
            ri.append(current_sample_ris)
    ri_norms = [[torch.norm(v).data[0] for v in ris] for ris in ri]
    return ri,ri_norms


def computeRiNaif(dataset,oppLabelData,oppLabel,layer,attributes,attribute_len):
    ri = []
    for batch in dataset:
        for sample in tqdm(batch):
            currentRis = list(map(lambda att : findCloserNaif(sample,oppLabelData,oppLabel,layer,
                                                              attributes.index(att),attribute_len),attributes))
            ri.append(currentRis)
    ri_norms = [[torch.norm(v).data[0] for v in ris] for ris in ri]
    return ri,ri_norms