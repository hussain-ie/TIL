

import tensorflow as tf
import numpy as np
import tqdm
from IPython.display import clear_output
import warnings , os
warnings.filterwarnings(action='ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
import tensorflow as tf
tf.logging.set_verbosity(tf.logging.ERROR)
import pickle 
import seaborn as sns
import matplotlib.pyplot as plt
import seaborn as sns 
##
np.random.seed(1234)

class Opt :
    def __init__(self , x_train , y_train , x_valid , y_valid , log_file , accbest , Bayes_iter , Save_dir ,
                 x_test , y_test , epoch_n , batch_size , cat_unique , cat_embed , use_embed ) :
        self.log_file = log_file
        self.x_train = x_train
        self.y_train = y_train ## 1 차원일떄 
        self.y_dim = y_train.shape[1]
        self.x_valid = x_valid
        self.y_valid = y_valid## 1 차원일떄 
        self.Bayes_iter = Bayes_iter
        self.accbest = accbest 
        self.Save_dir = Save_dir
        self.reportdir = self.Save_dir + "/Report_Opt.txt"
        self.x_test = x_test 
        self.y_test = y_test
        self.epoch_n = epoch_n
        self.batch_size = batch_size
        self.cat_unique  = cat_unique  
        self.cat_embed  = cat_embed 
        self.use_embed = use_embed
        self.active_dict = {0: "leaky_relu" , 1 : "relu" , 2 : "elu", 3 : "relu6" , 4 : "selu"}


    def activate(self , activation, first_layer, second_layer, bias  , keep_prob , is_training ):
            if activation == 0:
                activation = tf.nn.leaky_relu
            elif activation == 1:
                activation = tf.nn.relu
            elif activation == 2:
                activation = tf.nn.elu
            elif activation == 3:
                activation = tf.nn.relu6
            else :
                activation = tf.nn.selu
            layer = tf.matmul(first_layer, second_layer) + bias
            #layer = tf.contrib.layers.batch_norm(layer , center=True, scale=True,is_training=is_training)
            a = is_training
            layer = activation(layer)
            return tf.contrib.nn.alpha_dropout(layer, keep_prob)


    def focal_loss_sigmoid(self , labels,logits,alpha=0.25 , gamma=2):
        y_pred=tf.nn.sigmoid(logits)
        labels=tf.to_float(labels)
        L=-labels*(1-alpha)*((1-y_pred)*gamma)*tf.log(  tf.maximum(y_pred , 1e-14 )   )-\
          (1-labels)*alpha*(y_pred**gamma)*tf.log( tf.maximum( 1-y_pred ,  1e-14 ) ) 
        return L

    def neural_network(self , num_hidden, size_layer, learning_rate , dropout_rate,
                       activation , reduction_node , batch_size=256):

        print("Epoch N : {} , Batch Interation N : {}".format(self.epoch_n , 
                                                              self.x_train.shape[0] // self.batch_size))
        tf.reset_default_graph()
        tf.random.set_random_seed(1234)
        X = tf.placeholder(tf.float32, (None, self.x_train.shape[1]))
        Y = tf.placeholder(tf.float32, (None, self.y_train.shape[1]))# 
        keep_prob = tf.placeholder(tf.float32)
        is_training = tf.placeholder(tf.bool, name='phase')
        
        cat = tf.slice(X ,[0,0] , [-1 , len(self.use_embed) ] )
        cat = tf.cast(cat , tf.int32)
        firstcat = tf.slice(cat , [0,0] ,[-1, 1 ] )
        numericinput = tf.slice(X , [0 ,len(self.use_embed) ] ,[-1, -1 ] )
        firstcol = self.use_embed[0]
        cardinality = self.cat_unique.get(firstcol)
        embedding_size = self.cat_embed.get(firstcol)
        embeddings = tf.Variable(tf.random_uniform([cardinality, embedding_size], -1.0, 1.0))
        embedded_chars = tf.reshape(tf.nn.embedding_lookup(embeddings, firstcat), [-1 , embedding_size])
        for i , attr in enumerate(self.use_embed[1:]) :
            x2 = tf.slice(cat , [0, i] ,[-1, 1 ] )
            cardinality    = self.cat_unique.get(attr)
            embedding_size = self.cat_embed.get(attr)
            #embeddings = tf.Variable(tf.random_uniform([cardinality, embedding_size], -1.0 , 1.0)  , name= "embedw"  )
            embeddings =  tf.Variable(tf.contrib.layers.xavier_initializer()((cardinality , embedding_size )), name = "embedw")
            embedded_chars2 =  tf.nn.embedding_lookup(embeddings, x2 ,name = "lookup")                             
            embedded_chars2 = tf.reshape(embedded_chars2 , [-1 , embedding_size])
            embedded_chars = tf.concat([embedded_chars , embedded_chars2] , axis = 1)
        numinput = int(numericinput.shape[1])
        random = np.random.randint(2,4)
        numeric_hidden = tf.Variable(tf.contrib.layers.xavier_initializer()((numinput , numinput+random)), name = "Numeric_Hidden")
        numeric_bias = tf.Variable(tf.zeros([numinput+random]), name= "Numeric_Bias")
        NumericLayer = tf.matmul(numericinput , numeric_hidden) + numeric_bias
        firstlayer = tf.concat([embedded_chars , NumericLayer] , axis = 1)
        input_layer = tf.Variable(tf.contrib.layers.xavier_initializer()((numinput+ random +  sum(self.cat_embed.values()) , size_layer)))
        biased_layer = tf.Variable(tf.random_normal([size_layer], stddev = 0.01))
        
        #biased_output = tf.Variable(tf.random_normal([self.y_train.shape[1]], stddev = 0.1))


        layers, biased = [], []
        init_layer = size_layer
        layer_node_list = [size_layer +  sum(self.cat_embed.values()) , size_layer]
        for i in range(num_hidden - 1):
            size_layer2 = int(size_layer*2/3) + 2 
            layers.append(tf.Variable(tf.contrib.layers.xavier_initializer()((size_layer, size_layer2))))        
            biased.append(tf.Variable(tf.random_normal([size_layer2])))
            layer_node_list.append(size_layer2)
            size_layer = size_layer2
            
        first_l = self.activate(activation, firstlayer , input_layer, biased_layer , keep_prob , is_training) 
        next_l = self.activate(activation, first_l, layers[0], biased[0] , keep_prob , is_training)

        for i in range(1, num_hidden - 1):
            next_l = self.activate(activation, next_l, layers[i], biased[i] , keep_prob , is_training)
            
        output_layer = tf.Variable(tf.contrib.layers.xavier_initializer()((size_layer ,  self.y_train.shape[1] ))) # 
        last_l = tf.matmul(next_l, output_layer)
        # + biased_output
        cost  = tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(logits = last_l , labels = Y))
        optimizer = tf.train.AdamOptimizer(learning_rate).minimize(cost)

        if self.y_dim == 1 :
            pred_prob          = tf.nn.sigmoid(last_l)
            correct_prediction = tf.equal(tf.round(pred_prob), Y)
        else :
            pred_prob          = tf.nn.softmax(last_l)
            last_pred          = tf.argmax( last_l  , 1)
            last_y             = tf.argmax(Y, 1)
            correct_prediction = tf.equal(last_pred , last_y)
        
        
        accuracy           = tf.reduce_mean(tf.cast(correct_prediction, "float"))

        config=tf.ConfigProto(log_device_placement=False)
        config.gpu_options.allow_growth = True
        sess = tf.Session(config = config)
        sess.run(tf.global_variables_initializer())
## df[cat_columns] = df[cat_columns].apply(lambda x: x.cat.codes)

        COST, TEST_COST, ACC, TEST_ACC = [], [], [], []
        reduce_node = min( int(reduction_node) , 
                          int(np.around(init_layer) / np.around(num_hidden) )- 3  )
        print("num hidden layer : {}, layer : {} , lr : {}, dropout rate : {},  activation : {},  Reduction Node : {}"\
              .format(int(np.around(num_hidden)),
                      layer_node_list , learning_rate ,
                      dropout_rate  , self.active_dict.get(int(activation)) , reduce_node))
        
        for i in range(self.epoch_n) : 
            train_acc, train_loss = 0, 0
            train_dt = np.concatenate((self.x_train , self.y_train ) , axis = 1)
            print(np.shape(train_dt))
            np.random.shuffle(train_dt)
            x_train2 = train_dt[:, : -self.y_dim ]
            y_train2 = train_dt[:,   -self.y_dim :]
            print(y_train2[0:100,:])
            for n in range(0,  (self.x_train.shape[0] // self.batch_size) * self.batch_size,  self.batch_size):
                
                _, loss ,  ACC2  =\
                sess.run([optimizer, cost , accuracy ], 
                         feed_dict = {X: x_train2[n: n + self.batch_size, :],
                                      Y: y_train2[n: n + self.batch_size, :],
                                      keep_prob : dropout_rate ,
                                      is_training : 1})

                train_acc  += ACC2
                #accuracy_score(TRUE , PRED)
                train_loss += loss
            train_loss /= (x_train2.shape[0] // self.batch_size)
            train_acc /= (x_train2.shape[0] // self.batch_size)
            if i % 100 == 0 :
                print("Epoch : {} , Total Loss : {:.3f} , Train ACC : {:.3f}".format(i , train_loss , train_acc))
            ACC.append(train_acc)
            COST.append(train_loss)
        ## test는 학습 다하고 딱 한번만 하는 것이 맞지 않을까? 
        TEST_COST.append(sess.run(cost, feed_dict = {X: self.x_valid, 
                                                     Y: self.y_valid ,
                                                     keep_prob : 1.0 ,
                                                    is_training : 0}))
        test_acc = sess.run([accuracy], feed_dict = {X: self.x_valid,
                                                     Y: self.y_valid ,
                                                     keep_prob : 1.0  ,
                                                     is_training : 0
                                                    })
        TEST_ACC.append(test_acc)
        COST = np.array(COST).mean()
        ACC = np.array(ACC).mean()
        TEST_COST = np.array(TEST_COST).mean()
        TEST_ACC = np.array(TEST_ACC).mean()
        clear_output(wait=True)
        test_acc , prob = sess.run([accuracy , pred_prob ],
                                   feed_dict = {X: self.x_test , Y: self.y_test ,
                                                keep_prob : 1.0 , is_training : 0})
        output = [self.y_test , test_acc, prob]
        if TEST_ACC > self.accbest :
            f, ax = plt.subplots(figsize=(13,6))
            rainidx = self.y_test == 1
            sns.distplot(prob[~rainidx] , label ="NotRain")
            sns.distplot(prob[rainidx] , label ="Rain")
            plt.legend(fontsize= 15)
            plt.savefig(self.Save_dir + "/Plot/{}.png".format(self.Bayes_iter))
            plt.close()
            with open(self.Save_dir +  "/{}_test_result.p".format(self.Bayes_iter), "wb" ) as f :
                pickle.dump(output ,f )
        return COST, TEST_COST, ACC, TEST_ACC


    def generate_nn(self , num_hidden, size_layer, learning_rate, 
                    dropout_rate, activation , reduction_node):
        param = {
            'num_hidden'     : int(np.around(num_hidden)),
            'size_layer'     : int(np.around(size_layer)),
            'learning_rate'  : max(min(learning_rate, 1), 0.001),
            'dropout_rate'   : max(min(dropout_rate, 0.7), 0.2),
            'activation'     : int(np.around(activation)) , 
            "reduction_node" : min( int(reduction_node) , 
                                   int(np.around(size_layer) / np.around(num_hidden) )- 3  ) }
        
        print("\n Search parameters \n %s" % (param), file = self.log_file)
        
        self.log_file.flush()
        learning_cost, valid_cost, learning_acc, valid_acc = self.neural_network(**param)
        #print("stop after 5000 iteration with Train cost %f, Valid cost %f, Train acc %f, Valid acc %f" % (learning_cost, valid_cost, learning_acc, valid_acc))
        
        f = open(self.reportdir ,'a')
        result_ =\
        "BayesIter : {} Train cost {:.3f}, Valid cost {:.3f}, Train acc {:.3f}, Valid acc {:.3f} \n".\
        format(self.Bayes_iter , learning_cost, valid_cost, learning_acc, valid_acc)
        print(result_)
        self.Bayes_iter +=1
        f.write(result_)
        if (valid_acc > self.accbest ):
            self.accbest = valid_acc
        return valid_acc

## https://www.kaggle.com/realshijjang/tensorflow-binary-classification-with-sigmoid
## df[cat_columns] = df[cat_columns].apply(lambda x: x.cat.codes)
# def count_space_except_nan(x):
#     if isinstance(x,str):
#         return x.count(" ") + 1
#     else :
#         return 0
    
# def one_hot(df, cols):
#     """
#     @param df pandas DataFrame
#     @param cols a list of columns to encode 
#     @return a DataFrame with one-hot encoding
#     """
#     for each in cols:
#         dummies = pd.get_dummies(df[each], prefix=each, drop_first=False)
#         del df[each]
#         df = pd.concat([df, dummies], axis=1)
#     return df
