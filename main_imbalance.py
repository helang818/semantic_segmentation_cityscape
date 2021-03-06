from torchvision import utils
from basic_fcn import *
from dataloader_onehot import *
from utils import *
# from utils import *
import torchvision
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable
import time, os
import csv
from tqdm import tqdm, tqdm_notebook
import matplotlib.pyplot as plt
# import sys

torch.cuda.empty_cache()

if not os.path.isdir("./results"):
    os.system('mkdir ./results')

augment = [
    transforms.RandomCrop(320),
    transforms.RandomRotation((0,90)),
    transforms.RandomHorizontalFlip(0.5),
    transforms.RandomVerticalFlip(0.5)
]
tfs = transforms.Compose(augment)

augmentx = False # true, if augmentated dataset

if augmentx:
    aug_str = "aug"
    train_dataset = CityScapesDataset(csv_file='train.csv', transforms=tfs)
else:
    aug_str = ""
    train_dataset = CityScapesDataset(csv_file='train.csv', transforms=transforms.RandomCrop(512,512))
val_dataset = CityScapesDataset(csv_file='val.csv')
test_dataset = CityScapesDataset(csv_file='test.csv')
train_loader = DataLoader(dataset=train_dataset,
                          batch_size=2,
                          num_workers=0,
                          shuffle=True, 
                         )
val_loader = DataLoader(dataset=val_dataset,
                          batch_size=1,
                          num_workers=0,
                          shuffle=True)
test_loader = DataLoader(dataset=test_dataset,
                          batch_size=1,
                          num_workers=0,
                          shuffle=True)


def dice_loss(output, target):
    output = F.softmax(output, 1)
    numerator = 2 * torch.sum(output * target)
    denominator = torch.sum(output + target)
    return 1 - (numerator + 1) / (denominator + 1)

class diceLoss(torch.nn.Module):
    def __init__(self):
        super(diceLoss, self).__init__()
        
    def forward(self, output, target):
        return dice_loss(output, target)
    
d_criterion = diceLoss()

def init_weights(m):
    if isinstance(m, nn.Conv2d) or isinstance(m, nn.ConvTranspose2d):
        torch.nn.init.xavier_uniform_(m.weight.data)
#         torch.nn.init.xavier_uniform(m.bias.data, 0)
        nn.init.constant_(m.bias, 0)

# create directories to save trained models
if not os.path.isdir("./saved_models"):
    os.system("mkdir ./saved_models")

model_name = "dice_loss" # sub-directory name

if not os.path.isdir("./saved_models/%s"%(model_name)):
    os.system('mkdir ./saved_models/%s'%(model_name))
else:
    print("directory already exists")


n_class = 34
epochs = 20
criterion = nn.CrossEntropyLoss() # Choose an appropriate loss function from https://pytorch.org/docs/stable/_modules/torch/nn/modules/loss.html
# model = Resnet18(n_class=n_class)
model = FCN(n_class=n_class)
model.apply(init_weights)
# model.load_state_dict(torch.load('./saved_models/%s/resnet18_1'%(model_name)))
optimizer = optim.Adam(model.parameters(), lr=5e-3)


use_gpu = torch.cuda.is_available()
if use_gpu:
    print("GPU is available")
    model = model.cuda()
    
def train(init_epoch=0):
    train_losses = []
    val_losses = []
    prev_loss = -100
    loss_increase_counter = 0
    early_stop = True
    early_stop_threshold = 5
    for epoch in range(init_epoch, epochs):
        running_loss = 0.0
        ts = time.time()
        for iter, (X, tar, Y) in tqdm(enumerate(train_loader), desc ="Iteration num: "): # X=input_images, tar=one-hot labelled, y=segmentated
            optimizer.zero_grad()
            Y = Y.long()
            if use_gpu:
                inputs = X.cuda() # Move your inputs onto the gpu
                labels = Y.cuda() # Move your labels onto the gpu
                targets = tar.cuda()
                inputs.required_grad = False
                labels.required_grad = False
            else:
                inputs, targets, labels =  X, tar, Y # Unpack variables into inputs and labels
            outputs = model(inputs)
            loss = d_criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * inputs.size(0)
            if iter==5:
                break
            if iter % 50 == 0:
                print("epoch{}, iter{}, loss: {}".format(epoch, iter, loss.item()))
        
        print("Finish epoch {}, time elapsed {}".format(epoch, time.time() - ts))
        # os.system('rm -r ./saved_models/%s/*'%(model_name))
        torch.save(model.state_dict(), "./saved_models/%s/%s_%s_%d_%.3f"%(model_name,model_name,aug_str,epoch,loss.item()))
        train_loss = running_loss/len(train_loader)
        train_losses.append(train_loss)
        val_loss, val_pix_acc, avg_iou, ious = val(epoch)
        torch.cuda.empty_cache()
        val_losses.append(val_loss)
        with open("./results/"+model_name+"_results.csv",'a+', newline='') as csv_file:
            writer = csv.writer(csv_file, delimiter=',')
            # writer.writerow(["Epoch", "Train Loss", "Val Loss", "Val Pix Acc", "Val Avg IOU", "Val all IOU"])
            writer.writerow([epoch, train_loss,val_loss, val_pix_acc, avg_iou, ious])
        
        if val_loss > prev_loss:
            loss_increase_counter += 1
        else:
            loss_increase_counter = 0
        if early_stop and loss_increase_counter > early_stop_threshold:
            print("Early Stopping..")
            break
        prev_loss = val_loss

        model.train()
        torch.cuda.empty_cache()
        
    x = [i for i in range(epochs)]
    plt.title("ResNet: Plot of Training/Validation Loss vs # epochs")
    plt.xlabel("Number of epochs")
    plt.ylabel("Loss")
    plt.plot(x, train_losses, color='r', label='training loss')
    plt.plot(x, val_losses, color = 'b', label = 'validation loss')
    plt.grid(True)
    plt.legend()
    plt.savefig("./results/%s-loss.png"%(model_name))


def val(epoch):
    model.eval()

    #Complete this function - Calculate loss, accuracy and IoU for every epoch
    # Make sure to include a softmax after the output from your model
    # Evaluate
    total = 0
    correct = 0
    running_loss = 0.0
    
    inters = [0 for i in range(19)]
    unions = [0 for i in range(19)]
    for iter, (inputs, targets, labels) in tqdm(enumerate(val_loader)):
        inputs, targets, labels = inputs, targets.long(), labels.long()
        if use_gpu:
            inputs, targets, labels = inputs.cuda(), targets.cuda(), labels.cuda()

        outputs = model(inputs)
        loss = d_criterion(outputs, targets)
        running_loss += loss.item() * inputs.size(0)
        
        outputs = outputs.cpu()
        outputs = outputs.detach().numpy()
        labels = labels.cpu()
        labels = labels.detach().numpy()

        predict = np.argmax(outputs, axis = 1)
        correct = np.where(predict == labels, 1, 0).sum()
        total = predict.size
        val_pix_acc = 100.*correct/total
        
        curr_in, curr_un = iou(predict, labels)
        inters = [inters[p]+curr_in[p] for p in range(len(inters))]
        unions = [unions[p]+curr_un[p] for p in range(len(unions))]
        if iter == 5:
            break

    ious = [inters[p]/unions[p] if unions[p]!=0 else 0 for p in range(len(inters))]
    avg_iou = sum(inters)/sum(unions)        

    
    print('Epoch : %d Validation Pixel Acc : %.3f' % (epoch + 1, 100.*correct/total))
    print('--------------------------------------------------------------')
    print('Epoch : %d Validation Avg IOU : %.3f' % (epoch + 1, avg_iou))
    print('--------------------------------------------------------------')
    print("IOU values for each class at the end of epoch ", epoch+1," are:", ious)
    
    return (running_loss/len(val_loader)), val_pix_acc, avg_iou, ious

def test():
    model.eval() 
    #Complete this function - Calculate loss, accuracy and IoU for every epoch
    # Make sure to include a softmax after the output from your model
    # Evaluate
    total = 0
    correct = 0
    running_loss = 0.0
    
    inters = [0 for i in range(19)]
    unions = [0 for i in range(19)]
    for iter, (inputs, labels) in tqdm(enumerate(val_loader)):
        inputs, labels = inputs, labels.long()
        if use_gpu:
            inputs, labels = inputs.cuda(), labels.cuda()

        outputs = model(inputs)
        loss = criterion(outputs, labels)
        running_loss += loss.item() * inputs.size(0)
        
        outputs = outputs.cpu()
        outputs = outputs.detach().numpy()
        labels = labels.cpu()
        labels = labels.detach().numpy()

        predict = np.argmax(outputs, axis = 1)
        correct += np.where(predict == labels, 1, 0).sum()
        total += predict.size

        curr_in, curr_un = iou(predict, labels)
        inters = [inters[p]+curr_in[p] for p in range(len(inters))]
        unions = [unions[p]+curr_un[p] for p in range(len(unions))]
        if iter == 5:
            break

    ious = [inters[p]/unions[p] if unions[p]!=0 else 0 for p in range(len(inters))]
    avg_iou = sum(ious)/len(ious)
    test_acc = 100 * (correct/total)      
    
    print('Test Pixel Acc : %.3f' % (test_acc))
    print('--------------------------------------------------------------')
    print('Test Avg IOU : %.3f' % (avg_iou))
    print('--------------------------------------------------------------')
    print("Average Test IOU values for each class : ", ious)
    

    #Complete this function - Calculate accuracy and IoU 
    # Make sure to include a softmax after the output from your model
    
if __name__ == "__main__":
    val_loss_0 = val(0)  # show the accuracy before training
    train(init_epoch=0)  # put last trained epoch number, if resuming the training
    test()

    print("validation loss at epoch 0 :", str(val_loss_0))
