import torch
from torchtext import data
from torchtext import datasets
from torchtext import datasets
import random
import torch.nn as nn
import spacy
import torch.optim as optim
import time


class RNN(nn.Module):
	def __init__(self, vocab_size, embedding_dim, hidden_dim, output_dim, n_layers,
	             bidirectional, dropout, pad_idx):
		super().__init__()

		self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=pad_idx)

		self.rnn = nn.LSTM(embedding_dim,
		                   hidden_dim,
		                   num_layers=n_layers,
		                   bidirectional=bidirectional,
		                   dropout=dropout)

		self.fc = nn.Linear(hidden_dim * 2, output_dim)

		self.dropout = nn.Dropout(dropout)

	def forward(self, text, text_lengths):
		# text = [sent len, batch size]

		embedded = self.dropout(self.embedding(text))

		# embedded = [sent len, batch size, emb dim]

		# pack sequence
		packed_embedded = nn.utils.rnn.pack_padded_sequence(embedded, text_lengths)

		packed_output, (hidden, cell) = self.rnn(packed_embedded)

		# unpack sequence
		output, output_lengths = nn.utils.rnn.pad_packed_sequence(packed_output)

		# output = [sent len, batch size, hid dim * num directions]
		# output over padding tokens are zero tensors

		# hidden = [num layers * num directions, batch size, hid dim]
		# cell = [num layers * num directions, batch size, hid dim]

		# concat the final forward (hidden[-2,:,:]) and backward (hidden[-1,:,:]) hidden layers
		# and apply dropout

		hidden = self.dropout(torch.cat((hidden[-2, :, :], hidden[-1, :, :]), dim=1))

		# hidden = [batch size, hid dim * num directions]

		return self.fc(hidden)


def train(model, iterator, optimizer, criterion):
	epoch_loss = 0
	epoch_acc = 0

	model.train()

	for batch in iterator:
		optimizer.zero_grad()

		text, text_lengths = batch.text

		predictions = model(text, text_lengths).squeeze(1)

		loss = criterion(predictions, batch.label)

		acc = binary_accuracy(predictions, batch.label)

		loss.backward()

		optimizer.step()

		epoch_loss += loss.item()
		epoch_acc += acc.item()

	return epoch_loss / len(iterator), epoch_acc / len(iterator)


def count_parameters(model):
	return sum(p.numel() for p in model.parameters() if p.requires_grad)


def evaluate(model, iterator, criterion):
	epoch_loss = 0
	epoch_acc = 0

	model.eval()

	with torch.no_grad():
		for batch in iterator:
			text, text_lengths = batch.text

			predictions = model(text, text_lengths).squeeze(1)

			loss = criterion(predictions, batch.label)

			acc = binary_accuracy(predictions, batch.label)

			epoch_loss += loss.item()
			epoch_acc += acc.item()

	return epoch_loss / len(iterator), epoch_acc / len(iterator)


def epoch_time(start_time, end_time):
	elapsed_time = end_time - start_time
	elapsed_mins = int(elapsed_time / 60)
	elapsed_secs = int(elapsed_time - (elapsed_mins * 60))
	return elapsed_mins, elapsed_secs


def predict_sentiment(model, sentence):
	model.eval()
	tokenized = [tok.text for tok in nlp.tokenizer(sentence)]
	indexed = [TEXT.vocab.stoi[t] for t in tokenized]
	length = [len(indexed)]
	tensor = torch.LongTensor(indexed).to(device)
	tensor = tensor.unsqueeze(1)
	length_tensor = torch.LongTensor(length)
	prediction = torch.sigmoid(model(tensor, length_tensor))
	return prediction.item()


def binary_accuracy(preds, y):
	"""
	Returns accuracy per batch, i.e. if you get 8/10 right, this returns 0.8, NOT 8
	"""

	# round predictions to the closest integer
	rounded_preds = torch.round(torch.sigmoid(preds))
	correct = (rounded_preds == y).float()  # convert into float for division
	acc = correct.sum() / len(correct)
	return acc


nlp = spacy.load('en_core_web_sm')

SEED = 1234
MAX_VOCAB_SIZE = 25_000
BATCH_SIZE = 64
EMBEDDING_DIM = 100
HIDDEN_DIM = 256
OUTPUT_DIM = 1
N_LAYERS = 2
BIDIRECTIONAL = True
DROPOUT = 0.5
N_EPOCHS = 5

torch.manual_seed(SEED)
torch.backends.cudnn.deterministic = True

TEXT = data.Field(tokenize='spacy', include_lengths=True, tokenizer_language='en_core_web_sm')
LABEL = data.LabelField(dtype=torch.float)
print("h")
train_data, test_data = datasets.IMDB.splits(TEXT, LABEL)

train_data, valid_data = train_data.split(random_state=random.seed(SEED))

PAD_IDX = TEXT.vocab.stoi[TEXT.pad_token]
INPUT_DIM = len(TEXT.vocab)

TEXT.build_vocab(train_data,
                 max_size=MAX_VOCAB_SIZE,
                 vectors="glove.6B.100d",
                 unk_init=torch.Tensor.normal_)

LABEL.build_vocab(train_data)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

train_iterator, valid_iterator, test_iterator = data.BucketIterator.splits(
	(train_data, valid_data, test_data),
	batch_size=BATCH_SIZE,
	sort_within_batch=True,
	device=device)

model = RNN(INPUT_DIM,
            EMBEDDING_DIM,
            HIDDEN_DIM,
            OUTPUT_DIM,
            N_LAYERS,
            BIDIRECTIONAL,
            DROPOUT,
            PAD_IDX)

print(f'The model has {count_parameters(model):,} trainable parameters')

pretrained_embeddings = TEXT.vocab.vectors

print(pretrained_embeddings.shape)

model.embedding.weight.data.copy_(pretrained_embeddings)

UNK_IDX = TEXT.vocab.stoi[TEXT.unk_token]

model.embedding.weight.data[UNK_IDX] = torch.zeros(EMBEDDING_DIM)
model.embedding.weight.data[PAD_IDX] = torch.zeros(EMBEDDING_DIM)

print(model.embedding.weight.data)

optimizer = optim.Adam(model.parameters())

criterion = nn.BCEWithLogitsLoss()

model = model.to(device)
criterion = criterion.to(device)

best_valid_loss = float('inf')

for epoch in range(N_EPOCHS):

	start_time = time.time()

	train_loss, train_acc = train(model, train_iterator, optimizer, criterion)
	valid_loss, valid_acc = evaluate(model, valid_iterator, criterion)

	end_time = time.time()

	epoch_mins, epoch_secs = epoch_time(start_time, end_time)

	if valid_loss < best_valid_loss:
		best_valid_loss = valid_loss
		torch.save(model.state_dict(), 'tut2-model.pt')

	print(f'Epoch: {epoch+1:02} | Epoch Time: {epoch_mins}m {epoch_secs}s')
	print(f'\tTrain Loss: {train_loss:.3f} | Train Acc: {train_acc*100:.2f}%')
	print(f'\t Val. Loss: {valid_loss:.3f} |  Val. Acc: {valid_acc*100:.2f}%')

model.load_state_dict(torch.load('tut2-model.pt'))

test_loss, test_acc = evaluate(model, test_iterator, criterion)

print(f'Test Loss: {test_loss:.3f} | Test Acc: {test_acc*100:.2f}%')

predict_sentiment(model, "This film is terrible")

predict_sentiment(model,
                  "Quentin Tarantino returns, refreshed, with this funny, beautiful period piece, wrapping his story's loopy laces around movie lore and history, and mixing life and art into a cool, wild collage")
