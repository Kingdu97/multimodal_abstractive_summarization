from torch.utils.data import Dataset, DataLoader
from transformers import BartTokenizer, T5Tokenizer
from tqdm import tqdm
import pytorch_lightning as pl
import torch
import numpy as np
from utils.utils import pad_sents, get_mask

class OurDataset(Dataset):
    """Summarization dataset"""
    def __init__(self, args, mode):
        self.args = args
        # initial tokenizer and text
        if 't5' in self.args.model:
            self.tokenizer = T5Tokenizer.from_pretrained('t5-base')
        else:
            self.tokenizer = BartTokenizer.from_pretrained('facebook/bart-base')
        if mode == 'train':
            src_path = args.train_src_path
            tgt_path = args.train_tgt_path
        if mode == 'val':
            src_path = args.val_src_path
            tgt_path = args.val_tgt_path
        if mode == 'test':
            src_path = args.test_src_path
            tgt_path = args.test_tgt_path
        self.src = self.file_reader(src_path)   # 소스와 타겟 파일을 각각 읽어와 리스트로 저장
        self.tgt = self.file_reader(tgt_path)
        self.data_id = [item.split()[0] for item in self.tgt]   # 각 라인에서 문서 id 추출 -> data_id 리스트로 저장
        self.src = [" ".join(item.split()[1:]) for item in self.src] # 소스와 타겟 데이터에서 각 라인의 첫번째 단어를 제외한
        self.tgt = [" ".join(item.split()[1:]) for item in self.tgt] # 나머지 단어들을 다시 연결하여 문장으로 만듬
        # get tokenized test
        print('==================== Tokening {} set ======================'.format(mode))
        self.src_ids = self.tokenize(self.src)
        self.tgt_ids = self.tokenize(self.tgt)

    # __len__과 __getitem__ 메소드를 통해 데이터셋의 크기와 인덱스를 통해 데이터를 가져오는 기능
    def __len__(self):
        return len(self.src)    # 데이터셋의 크기를 반환. self.src의 길이와 같다.

    def __getitem__(self, idx):
        return self.src_ids[idx], self.tgt_ids[idx], self.data_id[idx]

    def tokenize(self, data):
        tokenized_text = [self.tokenizer.encode(i, add_special_tokens=False) for i in tqdm(data)]
        return tokenized_text
        # tqdm : python에서 진행 상황을 표시하는 라이브러리. 작업의 진행률을 표시해줌

    def file_reader(self, file_path):
        file = open(file_path, 'r')
        lines = [item.strip('\n') for item in file.readlines()]
        return lines

    def collate_fn(self, data):
        if self.args.model == 'text_only_bart':
            # rebuild the raw text and truncate to max length
            max_input_len = self.args.max_input_len
            max_output_len = self.args.max_output_len
            raw_src = [pair[0] for pair in data]
            raw_tgt = [pair[1] for pair in data]
            raw_src = [i[:max_input_len-1] for i in raw_src]
            raw_tgt = [i[:max_output_len-1] for i in raw_tgt]
            src = []
            tgt = []
            # remove blank data
            for i in range(len(raw_src)):
                src.append(raw_src[i])
                tgt.append(raw_tgt[i])
            # make input mask
            mask = torch.tensor(get_mask(src, max_len=max_input_len))
            # make input ids
            src_ids = torch.tensor(pad_sents(src, 1, max_len=max_input_len)[0])
            # make output ids
            decoder_ids = [[0]+i for i in tgt]
            # make output labels
            label_ids = [i+[2] for i in tgt]
            decoder_ids = torch.tensor(pad_sents(decoder_ids, 1, max_len=max_output_len)[0])
            label_ids = torch.tensor(pad_sents(label_ids, -100, max_len=max_output_len)[0])

            return src_ids, decoder_ids, mask, label_ids

        elif self.args.model == 'multi_modal_bart':
            # rebuild the raw text and truncate to max length
            max_input_len = self.args.max_input_len
            max_output_len = self.args.max_output_len
            max_img_len = self.args.max_img_len
            raw_src = [pair[0] for pair in data]
            raw_tgt = [pair[1] for pair in data]
            data_id = [pair[2] for pair in data]
            raw_src = [i[:max_input_len-1] for i in raw_src]
            raw_tgt = [i[:max_output_len-1] for i in raw_tgt]
            src = []
            tgt = []
            img = np.zeros([len(raw_src), self.args.max_img_len, 2048])
            img_len = []
            # remove blank data
            for i in range(len(raw_src)):
                src.append(raw_src[i])
                tgt.append(raw_tgt[i])
                image_feature = np.load(self.args.image_feature_path + data_id[i]+ '.npy')[:max_img_len]
                img[i][:image_feature.shape[0]] = image_feature
                img_len.append(image_feature.shape[0])
            img = img[:,:max(img_len)]

            # make input mask
            mask = torch.tensor(get_mask(src, max_len=max_input_len))
            # make input ids
            src_ids = torch.tensor(pad_sents(src, 1, max_len=max_input_len)[0])
            # make output ids
            decoder_ids = [[0]+i for i in tgt]
            # make output labels
            label_ids = [i+[2] for i in tgt]
            decoder_ids = torch.tensor(pad_sents(decoder_ids, 1, max_len=max_output_len)[0])
            label_ids = torch.tensor(pad_sents(label_ids, -100, max_len=max_output_len)[0])
            return src_ids, decoder_ids, mask, label_ids, torch.tensor(img), img_len
        
        #########################################################################
        ###############  Proposed model 여기가 새롭게 추가  #####################
        #########################################################################

        elif self.args.model == 'tri_modal_bart':
            # rebuild the raw text and truncate to max length
            max_input_len = self.args.max_input_len     # text input 512
            max_output_len = self.args.max_output_len   # text output 64
            max_img_len = self.args.max_img_len         # img_feature의 최대 길이 256
            max_aud_len = self.args.max_aud_len         # aud_feature의 최대 길이 256 근데, 미정
            raw_src = [pair[0] for pair in data]
            raw_tgt = [pair[1] for pair in data]
            data_id = [pair[2] for pair in data]
            raw_src = [i[:max_input_len-1] for i in raw_src]
            raw_tgt = [i[:max_output_len-1] for i in raw_tgt]
            src = []
            tgt = []
            img = np.zeros([len(raw_src), self.args.max_img_len, 2048]) # img는 크기가 (len(raw_src), self.args.max_img_len, 2048)인 3차원 배열입니다. 
                                                                        # 배열의 모든 요소는 0으로 초기화됩니다. 이 배열은 이미지 데이터를 저장하기 위한 용도로 사용될 것입니다
            img_len = []

            aud = np.zeros([len(raw_src), self.args.max_aud_len, 43]) # aud는 43차원으로 통일이기 때문
            aud_len = []

            # remove blank data
            for i in range(len(raw_src)):
                src.append(raw_src[i])
                tgt.append(raw_tgt[i])
                image_feature = np.load(self.args.image_feature_path + data_id[i]+ '.npy')[:max_img_len]
                img[i][:image_feature.shape[0]] = image_feature
                img_len.append(image_feature.shape[0])
            img = img[:,:max(img_len)]

            # 위 i와 아래 i는 서로 독립이기때문에 해당루프 범위 내에서만 가능함!
            for i in range(len(raw_src)):
                src.append(raw_src[i])
                tgt.append(raw_tgt[i])
                audio_feature = np.load(self.args.audio_feature_path + data_id[i]+ '.npy')[:max_aud_len]
                aud[i][:audio_feature.shape[0]] = audio_feature
                aud_len.append(audio_feature.shape[0])
            aud = aud[:,:max(aud_len)]

            # make input mask
            mask = torch.tensor(get_mask(src, max_len=max_input_len))
            # make input ids
            src_ids = torch.tensor(pad_sents(src, 1, max_len=max_input_len)[0])
            # make output ids
            decoder_ids = [[0]+i for i in tgt]
            # make output labels
            label_ids = [i+[2] for i in tgt]
            decoder_ids = torch.tensor(pad_sents(decoder_ids, 1, max_len=max_output_len)[0])
            label_ids = torch.tensor(pad_sents(label_ids, -100, max_len=max_output_len)[0])
            return src_ids, decoder_ids, mask, label_ids, torch.tensor(img), img_len, torch.tensor(aud), aud_len
        

        elif self.args.model == 'text_only_t5':
            # rebuild the raw text and truncate to max length
            max_input_len = self.args.max_input_len
            max_output_len = self.args.max_output_len
            raw_src = [pair[0] for pair in data]
            raw_tgt = [pair[1] for pair in data]
            raw_src = [i[:max_input_len-1] for i in raw_src]
            raw_tgt = [i[:max_output_len-1] for i in raw_tgt]
            src = []
            tgt = []
            # remove blank data
            for i in range(len(raw_src)):
                src.append(raw_src[i])
                tgt.append(raw_tgt[i])
            # make input mask
            mask = torch.tensor(get_mask(src, max_len=max_input_len))
            # make input ids
            src_ids = torch.tensor(pad_sents(src, 0, max_len=max_input_len)[0])
            # make output ids
            decoder_ids = [[0]+i for i in tgt]
            # make output labels
            label_ids = [i+[1] for i in tgt]
            decoder_ids = torch.tensor(pad_sents(decoder_ids, 0, max_len=max_output_len)[0])
            label_ids = torch.tensor(pad_sents(label_ids, -100, max_len=max_output_len)[0])

            return src_ids, decoder_ids, mask, label_ids

        elif self.args.model == 'multi_modal_t5':
            # rebuild the raw text and truncate to max length
            max_input_len = self.args.max_input_len
            max_output_len = self.args.max_output_len
            max_img_len = self.args.max_img_len
            raw_src = [pair[0] for pair in data]
            raw_tgt = [pair[1] for pair in data]
            data_id = [pair[2] for pair in data]
            raw_src = [i[:max_input_len-1] for i in raw_src]
            raw_tgt = [i[:max_output_len-1] for i in raw_tgt]
            src = []
            tgt = []
            img = np.zeros([len(raw_src), self.args.max_img_len, 2048])
            img_len = []
            # remove blank data
            for i in range(len(raw_src)):
                src.append(raw_src[i])
                tgt.append(raw_tgt[i])
                if self.args.vision_use_noise:
                    image_feature = np.load(self.args.image_feature_path + data_id[i] + '_noise.npy')[:max_img_len]
                else:
                    image_feature = np.load(self.args.image_feature_path + data_id[i] + '.npy')[:max_img_len]
                # image_feature = np.load(self.args.image_feature_path + data_id[i]+ '.npy')[:max_img_len]
                img[i][:image_feature.shape[0]] = image_feature
                img_len.append(image_feature.shape[0])
            img = img[:,:max(img_len)]

            # make input mask
            mask = torch.tensor(get_mask(src, max_len=max_input_len))
            # make input ids
            src_ids = torch.tensor(pad_sents(src, 0, max_len=max_input_len)[0])
            # make output ids
            decoder_ids = [[0]+i for i in tgt]
            # make output labels
            label_ids = [i+[1] for i in tgt]
            decoder_ids = torch.tensor(pad_sents(decoder_ids, 0, max_len=max_output_len)[0])
            label_ids = torch.tensor(pad_sents(label_ids, -100, max_len=max_output_len)[0])
            return src_ids, decoder_ids, mask, label_ids, torch.tensor(img), img_len

        else:
            raise ValueError("Invalid model")

# Create a dataloading module as per the PyTorch Lightning Docs
class SummaryDataModule(pl.LightningDataModule):
  def __init__(self, args):
    super().__init__()
    train_set = OurDataset(args, 'train')
    val_set = OurDataset(args, 'val')
    test_set = OurDataset(args, 'test')
    self.train_loader = DataLoader(dataset=train_set, \
                                    batch_size=args.batch_size, \
                                    num_workers=3, \
                                    shuffle=True, \
                                    collate_fn=train_set.collate_fn)
    self.val_loader = DataLoader(dataset=val_set, \
                                    batch_size=args.batch_size, \
                                    num_workers=3, \
                                    shuffle=False, \
                                    collate_fn=val_set.collate_fn)
    self.test_loader = DataLoader(dataset=test_set, \
                                    batch_size=args.batch_size, \
                                    num_workers=3, \
                                    shuffle=False, \
                                    collate_fn=test_set.collate_fn)

  def train_dataloader(self):
    return self.train_loader

  def val_dataloader(self):
    return self.val_loader

  def test_dataloader(self):
    return self.test_loader