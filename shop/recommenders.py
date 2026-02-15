import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from .models import UserActivity, Product

def get_recommendations(user):
    # 1. Fetch data from DB
    acts = UserActivity.objects.all().values('user_id', 'product_id', 'score')
    
    # Check if there is enough data to pivot
    if not acts or len(acts) < 2: 
        return Product.objects.all().order_by('?')[:4] # Return 4 random products
    
    df = pd.DataFrame(acts)
    
    # 2. Create User-Item Matrix
    matrix = df.pivot_table(index='user_id', columns='product_id', values='score').fillna(0)
    
    # 3. Compute Similarity
    item_sim = cosine_similarity(matrix.T)
    sim_df = pd.DataFrame(item_sim, index=matrix.columns, columns=matrix.columns)
    
    # 4. Get products the user has interacted with
    user_interacted_products = df[df['user_id'] == user.id]['product_id'].tolist()
    
    if not user_interacted_products:
        return Product.objects.all().order_by('?')[:4]

    # 5. Find similar products using modern pandas approach
    recommendations_list = []
    for p in user_interacted_products:
        if p in sim_df.index:
            recommendations_list.append(sim_df[p])
    
    if not recommendations_list:
        return Product.objects.all().order_by('?')[:4]

    # Combine all series into one
    recommendations = pd.concat(recommendations_list)
    
    # 6. Sort and Filter
    # Highest scores first, remove duplicates, and remove products user already saw
    rec_ids = recommendations.groupby(recommendations.index).sum().sort_values(ascending=False).index.tolist()
    final_ids = [i for i in rec_ids if i not in user_interacted_products][:4]
    
    return Product.objects.filter(id__in=final_ids)