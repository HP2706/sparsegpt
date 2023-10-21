import random

import numpy as np
import torch
from datasets import load_dataset
from transformers import AutoTokenizer, LlamaTokenizer, CodeLlamaTokenizer
import multiprocessing as mp
from functools import partial
import datasets

def tokenize_content(content, tokenizer):
    return tokenizer(content, return_tensors='pt').input_ids[0]

def set_seed(seed):
    np.random.seed(seed)
    torch.random.manual_seed(seed)

def get_tokenizer(model):
    if "codellama" in model.lower():
      print("using codellama tokenizer")
      tokenizer = CodeLlamaTokenizer.from_pretrained(model, use_fast=False)
      print("using codellama tokenizer" )
      if tokenizer.bos_token_id != 1 or tokenizer.eos_token_id != 2:
            try:
                tokenizer.bos_token_id = 1
                tokenizer.eos_token_id = 2
            except AttributeError:
                pass
    elif "llama" in model.lower():
        print("using llama tokenizer")
        tokenizer = LlamaTokenizer.from_pretrained(model, use_fast=False)
        # fix for transformer 4.28.0.dev0 compatibility
        if tokenizer.bos_token_id != 1 or tokenizer.eos_token_id != 2:
            try:
                tokenizer.bos_token_id = 1
                tokenizer.eos_token_id = 2
            except AttributeError:
                pass
    else:
        tokenizer = AutoTokenizer.from_pretrained(model, use_fast=False)
    return tokenizer


def get_wikitext2(nsamples, seed, seqlen, model, tokenizer):
    
    traindata = load_dataset('wikitext', 'wikitext-2-raw-v1', split='train')
    testdata = load_dataset('wikitext', 'wikitext-2-raw-v1', split='test')

    trainenc = tokenizer(" ".join(traindata['text']), return_tensors='pt')
    testenc = tokenizer("\n\n".join(testdata['text']), return_tensors='pt')

    random.seed(seed)
    trainloader = []
    for _ in range(nsamples):
        i = random.randint(0, trainenc.input_ids.shape[1] - seqlen - 1)
        j = i + seqlen
        inp = trainenc.input_ids[:, i:j]
        tar = inp.clone()
        tar[:, :-1] = -100
        trainloader.append((inp, tar))
    return trainloader, testenc

def get_ptb(nsamples, seed, seqlen, model, tokenizer):
    traindata = load_dataset('ptb_text_only', 'penn_treebank', split='train')
    testdata = load_dataset('ptb_text_only', 'penn_treebank', split='test')

    trainenc = tokenizer(" ".join(traindata['sentence']), return_tensors='pt')
    testenc = tokenizer(" ".join(testdata['sentence']), return_tensors='pt')

    random.seed(seed)
    trainloader = []
    for _ in range(nsamples):
        i = random.randint(0, trainenc.input_ids.shape[1] - seqlen - 1)
        j = i + seqlen
        inp = trainenc.input_ids[:, i:j]
        tar = inp.clone()
        tar[:, :-1] = -100
        trainloader.append((inp, tar))
    return trainloader, testenc

def get_c4(nsamples, seed, seqlen, model, tokenizer):
    traindata = load_dataset(
        'allenai/c4', 'allenai--c4', data_files={'train': 'en/c4-train.00000-of-01024.json.gz'}, split='train'
    )
    valdata = load_dataset(
        'allenai/c4', 'allenai--c4', data_files={'validation': 'en/c4-validation.00000-of-00008.json.gz'}, split='validation'
    )

    random.seed(seed)
    trainloader = []
    for _ in range(nsamples):
        while True:
            i = random.randint(0, len(traindata) - 1)
            trainenc = tokenizer(traindata[i]['text'], return_tensors='pt')
            if trainenc.input_ids.shape[1] > seqlen:
                break
        i = random.randint(0, trainenc.input_ids.shape[1] - seqlen - 1)
        j = i + seqlen
        inp = trainenc.input_ids[:, i:j]
        tar = inp.clone()
        tar[:, :-1] = -100
        trainloader.append((inp, tar))

    valenc = tokenizer(' '.join(valdata[:1100]['text']), return_tensors='pt')
    valenc = valenc.input_ids[:, :(256 * seqlen)]

    class TokenizerWrapper:
        def __init__(self, input_ids):
            self.input_ids = input_ids
    valenc = TokenizerWrapper(valenc)

    return trainloader, valenc




def get_code(nsamples, seed, seqlen, model, tokenizer):

    instruction = datasets.ReadInstruction('train', from_ = 0, to=0.001, unit= '%')
    traindata = load_dataset("codeparrot/codeparrot-clean-train", split = [instruction]) 
    valdata = load_dataset("codeparrot/codeparrot-clean-valid", split = [instruction]) 

    with mp.Pool(processes = mp.cpu_count()) as p:
        trainenc_list = p.map(partial(tokenize_content, tokenizer = tokenizer), traindata[0]['content'])
        valenc_list = p.map(partial(tokenize_content, tokenizer = tokenizer), valdata[0]['content'])


    random.seed(seed)
    trainloader = []

    for _ in range(nsamples):
        # Randomly select a sequence from the list of tokenized sequences for training data
        random_train_sequence = random.choice(trainenc_list)
        
        # Ensure the sequence is long enough
        if len(random_train_sequence) > seqlen:
            i = random.randint(0, len(random_train_sequence) - seqlen - 1)
            j = i + seqlen
            inp = random_train_sequence[i:j].unsqueeze(0)  # Add batch dimension
            tar = inp.clone()
            tar[:, :-1] = -100
            trainloader.append((inp, tar))
    return trainloader, valenc_list


def get_loaders(name, nsamples=128, seed=0, seqlen=2048, model=''):
    print("get_loaders")
    tokenizer = get_tokenizer(model)
    if 'wikitext2' in name:
        return get_wikitext2(nsamples, seed, seqlen, model, tokenizer)
    if 'ptb' in name:
        return get_ptb(nsamples, seed, seqlen, model, tokenizer)
    if 'c4' in name:
        return get_c4(nsamples, seed, seqlen, model, tokenizer)
    if 'code' in name:
        return get_code(nsamples, seed, seqlen, model, tokenizer)

