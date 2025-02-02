
# coding: utf-8

# # Boosting a decision stump
# 
# The goal of this notebook is to implement your own boosting module.
# 
# **Brace yourselves**! This is going to be a fun and challenging assignment.
# 
# 
# * Use SFrames to do some feature engineering.
# * Modify the decision trees to incorporate weights.
# * Implement Adaboost ensembling.
# * Use your implementation of Adaboost to train a boosted decision stump ensemble.
# * Evaluate the effect of boosting (adding more decision stumps) on performance of the model.
# * Explore the robustness of Adaboost to overfitting.
# 
# Let's get started!

# ## Fire up GraphLab Create

# Make sure you have the latest version of GraphLab Create **(1.8.3 or newer)**. Upgrade by
# ```
#    pip install graphlab-create --upgrade
# ```
# See [this page](https://dato.com/download/) for detailed instructions on upgrading.

# In[68]:

import graphlab
import matplotlib.pyplot as plt
get_ipython().magic(u'matplotlib inline')


# # Getting the data ready

# We will be using the same [LendingClub](https://www.lendingclub.com/) dataset as in the previous assignment.

# In[69]:

loans = graphlab.SFrame('lending-club-data.gl/')


# ### Extracting the target and the feature columns
# 
# We will now repeat some of the feature processing steps that we saw in the previous assignment:
# 
# First, we re-assign the target to have +1 as a safe (good) loan, and -1 as a risky (bad) loan.
# 
# Next, we select four categorical features: 
# 1. grade of the loan 
# 2. the length of the loan term
# 3. the home ownership status: own, mortgage, rent
# 4. number of years of employment.

# In[70]:

features = ['grade',              # grade of the loan
            'term',               # the term of the loan
            'home_ownership',     # home ownership status: own, mortgage or rent
            'emp_length',         # number of years of employment
           ]
loans['safe_loans'] = loans['bad_loans'].apply(lambda x : +1 if x==0 else -1)
loans.remove_column('bad_loans')
target = 'safe_loans'
loans = loans[features + [target]]


# ### Subsample dataset to make sure classes are balanced

# Just as we did in the previous assignment, we will undersample the larger class (safe loans) in order to balance out our dataset. This means we are throwing away many data points. We use `seed=1` so everyone gets the same results.

# In[71]:

safe_loans_raw = loans[loans[target] == 1]
risky_loans_raw = loans[loans[target] == -1]

# Undersample the safe loans.
percentage = len(risky_loans_raw)/float(len(safe_loans_raw))
risky_loans = risky_loans_raw
safe_loans = safe_loans_raw.sample(percentage, seed=1)
loans_data = risky_loans_raw.append(safe_loans)

print "Percentage of safe loans                 :", len(safe_loans) / float(len(loans_data))
print "Percentage of risky loans                :", len(risky_loans) / float(len(loans_data))
print "Total number of loans in our new dataset :", len(loans_data)


# **Note:** There are many approaches for dealing with imbalanced data, including some where we modify the learning algorithm. These approaches are beyond the scope of this course, but some of them are reviewed in this [paper](http://ieeexplore.ieee.org/xpl/login.jsp?tp=&arnumber=5128907&url=http%3A%2F%2Fieeexplore.ieee.org%2Fiel5%2F69%2F5173046%2F05128907.pdf%3Farnumber%3D5128907 ). For this assignment, we use the simplest possible approach, where we subsample the overly represented class to get a more balanced dataset. In general, and especially when the data is highly imbalanced, we recommend using more advanced methods.

# ### Transform categorical data into binary features

# In this assignment, we will work with **binary decision trees**. Since all of our features are currently categorical features, we want to turn them into binary features using 1-hot encoding. 
# 
# We can do so with the following code block (see the first assignments for more details):

# In[72]:

loans_data = risky_loans.append(safe_loans)
for feature in features:
    loans_data_one_hot_encoded = loans_data[feature].apply(lambda x: {x: 1})    
    loans_data_unpacked = loans_data_one_hot_encoded.unpack(column_name_prefix=feature)
    
    # Change None's to 0's
    for column in loans_data_unpacked.column_names():
        loans_data_unpacked[column] = loans_data_unpacked[column].fillna(0)

    loans_data.remove_column(feature)
    loans_data.add_columns(loans_data_unpacked)


# Let's see what the feature columns look like now:

# In[73]:

features = loans_data.column_names()
features.remove('safe_loans')  # Remove the response variable
features


# ### Train-test split
# 
# We split the data into training and test sets with 80% of the data in the training set and 20% of the data in the test set. We use `seed=1` so that everyone gets the same result.

# In[74]:

train_data, test_data = loans_data.random_split(0.8, seed=1)


# # Weighted decision trees

# Let's modify our decision tree code from Module 5 to support weighting of individual data points.

# ### Weighted error definition
# 
# Consider a model with $N$ data points with:
# * Predictions $\hat{y}_1 ... \hat{y}_n$ 
# * Target $y_1 ... y_n$ 
# * Data point weights $\alpha_1 ... \alpha_n$.
# 
# Then the **weighted error** is defined by:
# $$
# \mathrm{E}(\mathbf{\alpha}, \mathbf{\hat{y}}) = \frac{\sum_{i=1}^{n} \alpha_i \times 1[y_i \neq \hat{y_i}]}{\sum_{i=1}^{n} \alpha_i}
# $$
# where $1[y_i \neq \hat{y_i}]$ is an indicator function that is set to $1$ if $y_i \neq \hat{y_i}$.
# 
# 
# ### Write a function to compute weight of mistakes
# 
# Write a function that calculates the weight of mistakes for making the "weighted-majority" predictions for a dataset. The function accepts two inputs:
# * `labels_in_node`: Targets $y_1 ... y_n$ 
# * `data_weights`: Data point weights $\alpha_1 ... \alpha_n$
# 
# We are interested in computing the (total) weight of mistakes, i.e.
# $$
# \mathrm{WM}(\mathbf{\alpha}, \mathbf{\hat{y}}) = \sum_{i=1}^{n} \alpha_i \times 1[y_i \neq \hat{y_i}].
# $$
# This quantity is analogous to the number of mistakes, except that each mistake now carries different weight. It is related to the weighted error in the following way:
# $$
# \mathrm{E}(\mathbf{\alpha}, \mathbf{\hat{y}}) = \frac{\mathrm{WM}(\mathbf{\alpha}, \mathbf{\hat{y}})}{\sum_{i=1}^{n} \alpha_i}
# $$
# 
# The function **intermediate_node_weighted_mistakes** should first compute two weights: 
#  * $\mathrm{WM}_{-1}$: weight of mistakes when all predictions are $\hat{y}_i = -1$ i.e $\mathrm{WM}(\mathbf{\alpha}, \mathbf{-1}$)
#  * $\mathrm{WM}_{+1}$: weight of mistakes when all predictions are $\hat{y}_i = +1$ i.e $\mbox{WM}(\mathbf{\alpha}, \mathbf{+1}$)
#  
#  where $\mathbf{-1}$ and $\mathbf{+1}$ are vectors where all values are -1 and +1 respectively.
#  
# After computing $\mathrm{WM}_{-1}$ and $\mathrm{WM}_{+1}$, the function **intermediate_node_weighted_mistakes** should return the lower of the two weights of mistakes, along with the class associated with that weight. We have provided a skeleton for you with `YOUR CODE HERE` to be filled in several places.

# In[75]:

def intermediate_node_weighted_mistakes(labels_in_node, data_weights):
    # Sum the weights of all entries with label +1
    total_weight_positive = sum(data_weights[labels_in_node == +1])
    
    # Weight of mistakes for predicting all -1's is equal to the sum above
    ### YOUR CODE HERE
    weighted_mistakes_all_negative = total_weight_positive
    
    # Sum the weights of all entries with label -1
    ### YOUR CODE HERE
    total_weight_negative = sum(data_weights[labels_in_node == -1])
    
    # Weight of mistakes for predicting all +1's is equal to the sum above
    ### YOUR CODE HERE
    weighted_mistakes_all_positive = total_weight_negative
    
    # Return the tuple (weight, class_label) representing the lower of the two weights
    #    class_label should be an integer of value +1 or -1.
    # If the two weights are identical, return (weighted_mistakes_all_positive,+1)
    ### YOUR CODE HERE
    if weighted_mistakes_all_negative == weighted_mistakes_all_positive:
        return (weighted_mistakes_all_positive, +1)
    else:
        if weighted_mistakes_all_negative <= weighted_mistakes_all_positive:
            return (weighted_mistakes_all_negative, -1)
        else:
            return (weighted_mistakes_all_positive, +1)


# **Checkpoint:** Test your **intermediate_node_weighted_mistakes** function, run the following cell:

# In[76]:

example_labels = graphlab.SArray([-1, -1, 1, 1, 1])
example_data_weights = graphlab.SArray([1., 2., .5, 1., 1.])
if intermediate_node_weighted_mistakes(example_labels, example_data_weights) == (2.5, -1):
    print 'Test passed!'
else:
    print 'Test failed... try again!'


# Recall that the **classification error** is defined as follows:
# $$
# \mbox{classification error} = \frac{\mbox{# mistakes}}{\mbox{# all data points}}
# $$
# 
# **Quiz Question:** If we set the weights $\mathbf{\alpha} = 1$ for all data points, how is the weight of mistakes $\mbox{WM}(\mathbf{\alpha}, \mathbf{\hat{y}})$ related to the `classification error`?

# ### Function to pick best feature to split on

# We continue modifying our decision tree code from the earlier assignment to incorporate weighting of individual data points. The next step is to pick the best feature to split on.
# 
# The **best_splitting_feature** function is similar to the one from the earlier assignment with two minor modifications:
#   1. The function **best_splitting_feature** should now accept an extra parameter `data_weights` to take account of weights of data points.
#   2. Instead of computing the number of mistakes in the left and right side of the split, we compute the weight of mistakes for both sides, add up the two weights, and divide it by the total weight of the data.
#   
# Complete the following function. Comments starting with `DIFFERENT HERE` mark the sections where the weighted version differs from the original implementation.

# In[77]:

# If the data is identical in each feature, this function should return None

def best_splitting_feature(data, features, target, data_weights):
    
    # These variables will keep track of the best feature and the corresponding error
    best_feature = None
    best_error = float('+inf') 
    num_points = float(len(data))

    # Loop through each feature to consider splitting on that feature
    for feature in features:
        
        # The left split will have all data points where the feature value is 0
        # The right split will have all data points where the feature value is 1
        left_split = data[data[feature] == 0]
        right_split = data[data[feature] == 1]
        
        # Apply the same filtering to data_weights to create left_data_weights, right_data_weights
        ## YOUR CODE HERE
        left_data_weights = data_weights[data[feature] == 0]
        right_data_weights = data_weights[data[feature] == 1]
                    
        # DIFFERENT HERE
        # Calculate the weight of mistakes for left and right sides
        ## YOUR CODE HERE
        left_weighted_mistakes, left_class = intermediate_node_weighted_mistakes(left_split[target],
                                            left_data_weights)
        right_weighted_mistakes, right_class = intermediate_node_weighted_mistakes(right_split[target],
                                                                            right_data_weights)
        
        # DIFFERENT HERE
        # Compute weighted error by computing
        #  ( [weight of mistakes (left)] + [weight of mistakes (right)] ) / [total weight of all data points]
        ## YOUR CODE HERE
        error = (left_weighted_mistakes + right_weighted_mistakes)/(sum(left_data_weights) + sum(right_data_weights))
        
        # If this is the best error we have found so far, store the feature and the error
        if error < best_error:
            best_feature = feature
            best_error = error
    
    # Return the best feature we found
    return best_feature


# **Checkpoint:** Now, we have another checkpoint to make sure you are on the right track.

# In[78]:

example_data_weights = graphlab.SArray(len(train_data)* [1.5])
if best_splitting_feature(train_data, features, target, example_data_weights) == 'term. 36 months':
    print 'Test passed!'
else:
    print 'Test failed... try again!'


# **Note**. If you get an exception in the line of "the logical filter has different size than the array", try upgradting your GraphLab Create installation to 1.8.3 or newer.

# **Very Optional**. Relationship between weighted error and weight of mistakes
# 
# By definition, the weighted error is the weight of mistakes divided by the weight of all data points, so
# $$
# \mathrm{E}(\mathbf{\alpha}, \mathbf{\hat{y}}) = \frac{\sum_{i=1}^{n} \alpha_i \times 1[y_i \neq \hat{y_i}]}{\sum_{i=1}^{n} \alpha_i} = \frac{\mathrm{WM}(\mathbf{\alpha}, \mathbf{\hat{y}})}{\sum_{i=1}^{n} \alpha_i}.
# $$
# 
# In the code above, we obtain $\mathrm{E}(\mathbf{\alpha}, \mathbf{\hat{y}})$ from the two weights of mistakes from both sides, $\mathrm{WM}(\mathbf{\alpha}_{\mathrm{left}}, \mathbf{\hat{y}}_{\mathrm{left}})$ and $\mathrm{WM}(\mathbf{\alpha}_{\mathrm{right}}, \mathbf{\hat{y}}_{\mathrm{right}})$. First, notice that the overall weight of mistakes $\mathrm{WM}(\mathbf{\alpha}, \mathbf{\hat{y}})$ can be broken into two weights of mistakes over either side of the split:
# $$
# \mathrm{WM}(\mathbf{\alpha}, \mathbf{\hat{y}})
# = \sum_{i=1}^{n} \alpha_i \times 1[y_i \neq \hat{y_i}]
# = \sum_{\mathrm{left}} \alpha_i \times 1[y_i \neq \hat{y_i}]
#  + \sum_{\mathrm{right}} \alpha_i \times 1[y_i \neq \hat{y_i}]\\
# = \mathrm{WM}(\mathbf{\alpha}_{\mathrm{left}}, \mathbf{\hat{y}}_{\mathrm{left}}) + \mathrm{WM}(\mathbf{\alpha}_{\mathrm{right}}, \mathbf{\hat{y}}_{\mathrm{right}})
# $$
# We then divide through by the total weight of all data points to obtain $\mathrm{E}(\mathbf{\alpha}, \mathbf{\hat{y}})$:
# $$
# \mathrm{E}(\mathbf{\alpha}, \mathbf{\hat{y}})
# = \frac{\mathrm{WM}(\mathbf{\alpha}_{\mathrm{left}}, \mathbf{\hat{y}}_{\mathrm{left}}) + \mathrm{WM}(\mathbf{\alpha}_{\mathrm{right}}, \mathbf{\hat{y}}_{\mathrm{right}})}{\sum_{i=1}^{n} \alpha_i}
# $$

# ### Building the tree
# 
# With the above functions implemented correctly, we are now ready to build our decision tree. Recall from the previous assignments that each node in the decision tree is represented as a dictionary which contains the following keys:
# 
#     { 
#        'is_leaf'            : True/False.
#        'prediction'         : Prediction at the leaf node.
#        'left'               : (dictionary corresponding to the left tree).
#        'right'              : (dictionary corresponding to the right tree).
#        'features_remaining' : List of features that are posible splits.
#     }
#     
# Let us start with a function that creates a leaf node given a set of target values:

# In[79]:

def create_leaf(target_values, data_weights):
    
    # Create a leaf node
    leaf = {'splitting_feature' : None,
            'is_leaf': True}
    
    # Computed weight of mistakes.
    weighted_error, best_class = intermediate_node_weighted_mistakes(target_values, data_weights)
    # Store the predicted class (1 or -1) in leaf['prediction']
    leaf['prediction'] = best_class #label is in the second
    
    return leaf 


# We provide a function that learns a weighted decision tree recursively and implements 3 stopping conditions:
# 1. All data points in a node are from the same class.
# 2. No more features to split on.
# 3. Stop growing the tree when the tree depth reaches **max_depth**. 

# In[114]:

def weighted_decision_tree_create(data, features, target, data_weights, current_depth = 1, max_depth = 10):
    remaining_features = features[:] # Make a copy of the features.
    target_values = data[target]
    print "--------------------------------------------------------------------"
    print "Subtree, depth = %s (%s data points)." % (current_depth, len(target_values))
    
    # Stopping condition 1. Error is 0.
    if intermediate_node_weighted_mistakes(target_values, data_weights)[0] <= 1e-15:
        print "Stopping condition 1 reached."                
        return create_leaf(target_values, data_weights)
    
    # Stopping condition 2. No more features.
    if remaining_features == []:
        print "Stopping condition 2 reached."                
        return create_leaf(target_values, data_weights)    
    
    # Additional stopping condition (limit tree depth)
    if current_depth > max_depth:
        print "Reached maximum depth. Stopping for now."
        return create_leaf(target_values, data_weights)
    
    # If all the datapoints are the same, splitting_feature will be None. Create a leaf
    splitting_feature = best_splitting_feature(data, features, target, data_weights)
    remaining_features.remove(splitting_feature)
        
    left_split = data[data[splitting_feature] == 0]
    right_split = data[data[splitting_feature] == 1]
    
    left_data_weights = data_weights[data[splitting_feature] == 0]
    right_data_weights = data_weights[data[splitting_feature] == 1]
    
    print "Split on feature %s. (%s, %s)" % (              splitting_feature, len(left_split), len(right_split))
    
    # Create a leaf node if the split is "perfect"
    if len(left_split) == len(data):
        print "Creating leaf node."
        return create_leaf(left_split[target], data_weights)
    if len(right_split) == len(data):
        print "Creating leaf node."
        return create_leaf(right_split[target], data_weights)
    
    # Repeat (recurse) on left and right subtrees
    left_tree = weighted_decision_tree_create(
        left_split, remaining_features, target, left_data_weights, current_depth + 1, max_depth)
    right_tree = weighted_decision_tree_create(
        right_split, remaining_features, target, right_data_weights, current_depth + 1, max_depth)
    
    return {'is_leaf'          : False, 
            'prediction'       : None,
            'splitting_feature': splitting_feature,
            'left'             : left_tree, 
            'right'            : right_tree}


# Here is a recursive function to count the nodes in your tree:

# In[115]:

def count_nodes(tree):
    if tree['is_leaf']:
        return 1
    return 1 + count_nodes(tree['left']) + count_nodes(tree['right'])


# Run the following test code to check your implementation. Make sure you get **'Test passed'** before proceeding.

# In[116]:

example_data_weights = graphlab.SArray([1.0 for i in range(len(train_data))])
small_data_decision_tree = weighted_decision_tree_create(train_data, features, target,
                                        example_data_weights, max_depth=2)
if count_nodes(small_data_decision_tree) == 7:
    print 'Test passed!'
else:
    print 'Test failed... try again!'
    print 'Number of nodes found:', count_nodes(small_data_decision_tree)
    print 'Number of nodes that should be there: 7' 


# Let us take a quick look at what the trained tree is like. You should get something that looks like the following
# 
# ```
# {'is_leaf': False,
#     'left': {'is_leaf': False,
#         'left': {'is_leaf': True, 'prediction': -1, 'splitting_feature': None},
#         'prediction': None,
#         'right': {'is_leaf': True, 'prediction': 1, 'splitting_feature': None},
#         'splitting_feature': 'grade.A'
#      },
#     'prediction': None,
#     'right': {'is_leaf': False,
#         'left': {'is_leaf': True, 'prediction': 1, 'splitting_feature': None},
#         'prediction': None,
#         'right': {'is_leaf': True, 'prediction': -1, 'splitting_feature': None},
#         'splitting_feature': 'grade.D'
#      },
#      'splitting_feature': 'term. 36 months'
# }```

# In[117]:

small_data_decision_tree


# ### Making predictions with a weighted decision tree

# We give you a function that classifies one data point. It can also return the probability if you want to play around with that as well.

# In[118]:

def classify(tree, x, annotate = False):   
    # If the node is a leaf node.
    if tree['is_leaf']:
        if annotate: 
            print "At leaf, predicting %s" % tree['prediction']
        return tree['prediction'] 
    else:
        # Split on feature.
        split_feature_value = x[tree['splitting_feature']]
        if annotate: 
            print "Split on %s = %s" % (tree['splitting_feature'], split_feature_value)
        if split_feature_value == 0:
            return classify(tree['left'], x, annotate)
        else:
            return classify(tree['right'], x, annotate)


# ### Evaluating the tree
# 
# Now, we will write a function to evaluate a decision tree by computing the classification error of the tree on the given dataset.
# 
# Again, recall that the **classification error** is defined as follows:
# $$
# \mbox{classification error} = \frac{\mbox{# mistakes}}{\mbox{# all data points}}
# $$
# 
# The function called **evaluate_classification_error** takes in as input:
# 1. `tree` (as described above)
# 2. `data` (an SFrame)
# 
# The function does not change because of adding data point weights.

# In[119]:

def evaluate_classification_error(tree, data):
    # Apply the classify(tree, x) to each row in your data
    prediction = data.apply(lambda x: classify(tree, x))
    
    # Once you've made the predictions, calculate the classification error
    return (prediction != data[target]).sum() / float(len(data))


# In[120]:

evaluate_classification_error(small_data_decision_tree, test_data)


# ### Example: Training a weighted decision tree
# 
# To build intuition on how weighted data points affect the tree being built, consider the following:
# 
# Suppose we only care about making good predictions for the **first 10 and last 10 items** in `train_data`, we assign weights:
# * 1 to the last 10 items 
# * 1 to the first 10 items 
# * and 0 to the rest. 
# 
# Let us fit a weighted decision tree with `max_depth = 2`.

# In[121]:

# Assign weights
example_data_weights = graphlab.SArray([1.] * 10 + [0.]*(len(train_data) - 20) + [1.] * 10)

# Train a weighted decision tree model.
small_data_decision_tree_subset_20 = weighted_decision_tree_create(train_data, features, target,
                         example_data_weights, max_depth=2)


# Now, we will compute the classification error on the `subset_20`, i.e. the subset of data points whose weight is 1 (namely the first and last 10 data points).

# In[122]:

subset_20 = train_data.head(10).append(train_data.tail(10))
evaluate_classification_error(small_data_decision_tree_subset_20, subset_20)


# Now, let us compare the classification error of the model `small_data_decision_tree_subset_20` on the entire test set `train_data`:

# In[123]:

evaluate_classification_error(small_data_decision_tree_subset_20, train_data)


# The model `small_data_decision_tree_subset_20` performs **a lot** better on `subset_20` than on `train_data`.
# 
# So, what does this mean?
# * The points with higher weights are the ones that are more important during the training process of the weighted decision tree.
# * The points with zero weights are basically ignored during training.
# 
# **Quiz Question**: Will you get the same model as `small_data_decision_tree_subset_20` if you trained a decision tree with only the 20 data points with non-zero weights from the set of points in `subset_20`?

# # Implementing your own Adaboost (on decision stumps)

# Now that we have a weighted decision tree working, it takes only a bit of work to implement Adaboost. For the sake of simplicity, let us stick with **decision tree stumps** by training trees with **`max_depth=1`**.

# Recall from the lecture the procedure for Adaboost:
# 
# 1\. Start with unweighted data with $\alpha_j = 1$
# 
# 2\. For t = 1,...T:
#   * Learn $f_t(x)$ with data weights $\alpha_j$
#   * Compute coefficient $\hat{w}_t$:
#      $$\hat{w}_t = \frac{1}{2}\ln{\left(\frac{1- \mbox{E}(\mathbf{\alpha}, \mathbf{\hat{y}})}{\mbox{E}(\mathbf{\alpha}, \mathbf{\hat{y}})}\right)}$$
#   * Re-compute weights $\alpha_j$:
#      $$\alpha_j \gets \begin{cases}
#      \alpha_j \exp{(-\hat{w}_t)} & \text{ if }f_t(x_j) = y_j\\
#      \alpha_j \exp{(\hat{w}_t)} & \text{ if }f_t(x_j) \neq y_j
#      \end{cases}$$
#   * Normalize weights $\alpha_j$:
#       $$\alpha_j \gets \frac{\alpha_j}{\sum_{i=1}^{N}{\alpha_i}} $$
#   
# Complete the skeleton for the following code to implement **adaboost_with_tree_stumps**. Fill in the places with `YOUR CODE HERE`.

# In[124]:

from math import log
from math import exp

def adaboost_with_tree_stumps(data, features, target, num_tree_stumps):
    # start with unweighted data
    alpha = graphlab.SArray([1.]*len(data)) #weight ai being set to be same across all at the first iteration
    weights = []
    tree_stumps = []
    target_values = data[target]
    
    for t in xrange(num_tree_stumps):
        print '====================================================='
        print 'Adaboost Iteration %d' % t
        print '====================================================='        
        # Learn a weighted decision tree stump. Use max_depth=1
        tree_stump = weighted_decision_tree_create(data, features, target, data_weights=alpha, max_depth=1)
        tree_stumps.append(tree_stump)
        print alpha[5:10]
        # Make predictions
        predictions = data.apply(lambda x: classify(tree_stump, x))
        
        # Produce a Boolean array indicating whether
        # each data point was correctly classified
        is_correct = predictions == target_values
        is_wrong   = predictions != target_values
        
        # Compute weighted error
        # YOUR CODE HERE
        weighted_error = sum(alpha[is_wrong]) / sum(alpha)
        
        # Compute model coefficient using weighted error
        # YOUR CODE HERE
        weight = (1.0 / 2.0) * log((1-weighted_error)/ (weighted_error))
        weights.append(weight)
        
        # Adjust weights on data point
        adjustment = is_correct.apply(lambda is_correct : exp(-weight) if is_correct else exp(weight))
        
        # Scale alpha by multiplying by adjustment 
        # Then normalize data points weights
        ## YOUR CODE HERE 
        alpha = (alpha) * adjustment
    
    return weights, tree_stumps


# ### Checking your Adaboost code
# 
# Train an ensemble of **two** tree stumps and see which features those stumps split on. We will run the algorithm with the following parameters:
# * `train_data`
# * `features`
# * `target`
# * `num_tree_stumps = 2`

# In[125]:

stump_weights, tree_stumps = adaboost_with_tree_stumps(train_data, features, target, num_tree_stumps=2)


# In[126]:

def print_stump(tree):
    split_name = tree['splitting_feature'] # split_name is something like 'term. 36 months'
    if split_name is None:
        print "(leaf, label: %s)" % tree['prediction']
        return None
    split_feature, split_value = split_name.split('.')
    print '                       root'
    print '         |---------------|----------------|'
    print '         |                                |'
    print '         |                                |'
    print '         |                                |'
    print '  [{0} == 0]{1}[{0} == 1]    '.format(split_name, ' '*(27-len(split_name)))
    print '         |                                |'
    print '         |                                |'
    print '         |                                |'
    print '    (%s)                 (%s)'         % (('leaf, label: ' + str(tree['left']['prediction']) if tree['left']['is_leaf'] else 'subtree'),
           ('leaf, label: ' + str(tree['right']['prediction']) if tree['right']['is_leaf'] else 'subtree'))


# Here is what the first stump looks like:

# In[127]:

print_stump(tree_stumps[0])


# Here is what the next stump looks like:

# In[128]:

print_stump(tree_stumps[1])


# In[129]:

print stump_weights


# If your Adaboost is correctly implemented, the following things should be true:
# 
# * `tree_stumps[0]` should split on **term. 36 months** with the prediction -1 on the left and +1 on the right.
# * `tree_stumps[1]` should split on **grade.A** with the prediction -1 on the left and +1 on the right.
# * Weights should be approximately `[0.158, 0.177]` 
# 
# **Reminders**
# - Stump weights ($\mathbf{\hat{w}}$) and data point weights ($\mathbf{\alpha}$) are two different concepts.
# - Stump weights ($\mathbf{\hat{w}}$) tell you how important each stump is while making predictions with the entire boosted ensemble.
# - Data point weights ($\mathbf{\alpha}$) tell you how important each data point is while training a decision stump.

# ### Training a boosted ensemble of 10 stumps

# Let us train an ensemble of 10 decision tree stumps with Adaboost. We run the **adaboost_with_tree_stumps** function with the following parameters:
# * `train_data`
# * `features`
# * `target`
# * `num_tree_stumps = 10`

# In[130]:

stump_weights, tree_stumps = adaboost_with_tree_stumps(train_data, features, 
                                target, num_tree_stumps=10)


# ## Making predictions
# 
# Recall from the lecture that in order to make predictions, we use the following formula:
# $$
# \hat{y} = sign\left(\sum_{t=1}^T \hat{w}_t f_t(x)\right)
# $$
# 
# We need to do the following things:
# - Compute the predictions $f_t(x)$ using the $t$-th decision tree
# - Compute $\hat{w}_t f_t(x)$ by multiplying the `stump_weights` with the predictions $f_t(x)$ from the decision trees
# - Sum the weighted predictions over each stump in the ensemble.
# 
# Complete the following skeleton for making predictions:

# In[131]:

def predict_adaboost(stump_weights, tree_stumps, data):
    scores = graphlab.SArray([0.]*len(data))
    
    for i, tree_stump in enumerate(tree_stumps):
        predictions = data.apply(lambda x: classify(tree_stump, x))
        
        # Accumulate predictions on scores array
        #Because stump with more weight, the signficant one have higher effect in final
        scores += stump_weights[i] * predictions
        
    return scores.apply(lambda score : +1 if score > 0 else -1)


# In[132]:

predictions = predict_adaboost(stump_weights, tree_stumps, test_data)
accuracy = graphlab.evaluation.accuracy(test_data[target], predictions)
print 'Accuracy of 10-component ensemble = %s' % accuracy 


# Now, let us take a quick look what the `stump_weights` look like at the end of each iteration of the 10-stump ensemble:

# In[134]:

stump_weights


# **Quiz Question:** Are the weights monotonically decreasing, monotonically increasing, or neither?
# 
# **Reminder**: Stump weights ($\mathbf{\hat{w}}$) tell you how important each stump is while making predictions with the entire boosted ensemble.

# # Performance plots
# 
# In this section, we will try to reproduce some of the performance plots dicussed in the lecture.
# 
# ### How does accuracy change with adding stumps to the ensemble?
# 
# We will now train an ensemble with:
# * `train_data`
# * `features`
# * `target`
# * `num_tree_stumps = 30`
# 
# Once we are done with this, we will then do the following:
# * Compute the classification error at the end of each iteration.
# * Plot a curve of classification error vs iteration.
# 
# First, lets train the model.

# In[135]:

# this may take a while... 
stump_weights, tree_stumps = adaboost_with_tree_stumps(train_data, 
                                 features, target, num_tree_stumps=30)


# ### Computing training error at the end of each iteration
# 
# Now, we will compute the classification error on the **train_data** and see how it is reduced as trees are added.

# In[136]:

error_all = []
for n in xrange(1, 31):
    predictions = predict_adaboost(stump_weights[:n], tree_stumps[:n], train_data)
    error = 1.0 - graphlab.evaluation.accuracy(train_data[target], predictions)
    error_all.append(error)
    print "Iteration %s, training error = %s" % (n, error_all[n-1])


# ### Visualizing training error vs number of iterations
# 
# We have provided you with a simple code snippet that plots classification error with the number of iterations. 

# In[137]:

plt.rcParams['figure.figsize'] = 7, 5
plt.plot(range(1,31), error_all, '-', linewidth=4.0, label='Training error')
plt.title('Performance of Adaboost ensemble')
plt.xlabel('# of iterations')
plt.ylabel('Classification error')
plt.legend(loc='best', prop={'size':15})

plt.rcParams.update({'font.size': 16})


# **Quiz Question**: Which of the following best describes a **general trend in accuracy** as we add more and more components? Answer based on the 30 components learned so far.
# 
# 1. Training error goes down monotonically, i.e. the training error reduces with each iteration but never increases.
# 2. Training error goes down in general, with some ups and downs in the middle.
# 3. Training error goes up in general, with some ups and downs in the middle.
# 4. Training error goes down in the beginning, achieves the best error, and then goes up sharply.
# 5. None of the above
# 
# 
# ### Evaluation on the test data
# 
# Performing well on the training data is cheating, so lets make sure it works on the `test_data` as well. Here, we will compute the classification error on the `test_data` at the end of each iteration.

# In[138]:

test_error_all = []
for n in xrange(1, 31):
    predictions = predict_adaboost(stump_weights[:n], tree_stumps[:n], test_data)
    error = 1.0 - graphlab.evaluation.accuracy(test_data[target], predictions)
    test_error_all.append(error)
    print "Iteration %s, test error = %s" % (n, test_error_all[n-1])


# ### Visualize both the training and test errors
# 
# Now, let us plot the training & test error with the number of iterations.

# In[139]:

plt.rcParams['figure.figsize'] = 7, 5
plt.plot(range(1,31), error_all, '-', linewidth=4.0, label='Training error')
plt.plot(range(1,31), test_error_all, '-', linewidth=4.0, label='Test error')

plt.title('Performance of Adaboost ensemble')
plt.xlabel('# of iterations')
plt.ylabel('Classification error')
plt.rcParams.update({'font.size': 16})
plt.legend(loc='best', prop={'size':15})
plt.tight_layout()


# ** Quiz Question:** From this plot (with 30 trees), is there massive overfitting as the # of iterations increases?

# In[ ]:



