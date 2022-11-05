import copy
import gym
from pip import main
import numpy as np
import core
import torch
from torch.optim import Adam
import random

from memory import ReplayBuffer
torch.manual_seed(0)
np.random.seed(0)
env = gym.make("FetchReach-v1",reward_type="dense")

actor_critic=core.MLPActorCritic
ac_kwargs=dict()
ac = actor_critic(env.observation_space['observation'], env.action_space, **ac_kwargs)
alpha = 0.9
discount = 0.9
qnetwork =  copy.deepcopy(ac.q)
anetwork =  copy.deepcopy(ac.pi)
qtarget =  copy.deepcopy(qnetwork)
atarget = copy.deepcopy(anetwork)

# Set up optimizers for policy and q-function
pi_lr=1e-3
q_lr=1e-3
aoptimizer = Adam(anetwork.parameters(), lr=pi_lr)
qoptimizer = Adam(qnetwork.parameters(), lr=q_lr)

def get_action(o, noise_scale):
   
    act_limit = env.action_space.high[0]
    act_dim = env.action_space.shape[0]
    a = anetwork(torch.as_tensor(o, dtype=torch.float32)).detach().numpy()
    a += noise_scale * np.random.randn(act_dim)
    return np.clip(a, -act_limit, act_limit)

def compute_loss_q(data):
        gamma = 0.99
        o, a, r, o2, d = data['obs'], data['act'], data['rew'], data['obs2'], data['done']
        q = qnetwork(o,a)
        # Bellman backup for Q function
 
        with torch.no_grad():
            q_pi_targ = qtarget(o2, atarget(o2))
            backup = r + gamma * (1 - d) * (q_pi_targ )

        # MSE loss against Bellman backup
        loss_q = ((q - backup)**2).mean()
        return loss_q

# Set up function for computing DDPG pi loss
def compute_loss_pi(data):
    o = data['obs']
    a = data['act']
    q_pi = qnetwork(o, anetwork(o))
    return -q_pi.mean()

def main():
    dim_u = env.action_space.shape[0]
    print(dim_u)
    dim_o = env.observation_space["observation"].shape[0]
    print(dim_o)
    observation = env.reset()
    max_action = env.action_space.high
    print("max_action:", max_action)
    print("mmin_action", env.action_space.low)
    
    score_history = []
    n_played_games = 0
    start_episodes = 100
    
    # Experience buffer
    replay_size=int(1e6)
    obs_dim = env.observation_space['observation'].shape[0] + 3
    act_dim = env.action_space.shape[0]
    replay_buffer = ReplayBuffer(obs_dim=obs_dim, act_dim=act_dim, size=replay_size)

    goals = []
    observation,ep_ret,ep_len = env.reset(),0,0
    
    for episode in range(400):
        print(episode)
        if(episode == start_episodes):
            observation,ep_ret,ep_len = env.reset(),0,0
        goals = []
        
        for steps in range (1,100):        
            state = observation
            mstate = np.append(state['observation'],state['desired_goal'])
            
            a = env.action_space.sample()
            if episode > start_episodes:
                a = get_action(mstate, 0.1)
            else:
                a = env.action_space.sample()

            action = a
            observation, reward, done, info = env.step(action)
            
            sprime = observation
            msprime = np.append(observation['observation'],observation['desired_goal'])
            
            goals.append(sprime['achieved_goal'])
        
            ep_ret += reward
            ep_len += 1
            
            replay_buffer.store(mstate,action,reward,msprime,done)
            
            for goal in goals:
                nstate = np.append(state['observation'],goal)
                nsprime =  np.append(sprime['observation'],goal)
                reward = env.compute_reward(state['achieved_goal'], goal , info)
                replay_buffer.store(nstate,action,reward,nsprime,0)
           
            if (done or steps >= 999):
                n_played_games += 1
                score_history.append(ep_ret)
                avg_score = np.mean(score_history[-100:])
                print( 'score %.1f' %ep_ret, 'avg_score %.1f' %avg_score,'num_games', n_played_games, action )
                observation,ep_ret,ep_len= env.reset(), 0, 0
                break
            
            if(steps  % 1 == 0 and episode > 200):
               update(replay_buffer)
            
    while(1):
        test_agent()
            

def update(replay_buffer):
    batch_size = 500
    data = replay_buffer.sample_batch(batch_size)
    qoptimizer.zero_grad()
    loss = compute_loss_q(data)
    loss.backward()
    qoptimizer.step()
    
    
    for p in qnetwork.parameters():
        p.requires_grad = False

    # Next run one gradient descent step for pi.
    aoptimizer.zero_grad()
    loss_pi = compute_loss_pi(data)
    loss_pi.backward()
    aoptimizer.step()
    
    # Unfreeze Q-network so you can optimize it at next DDPG step.
    for p in qnetwork.parameters():
        p.requires_grad = True

    polyak = 0.995
    for t, n in zip(qtarget.parameters(),qnetwork.parameters()):
        t.data.mul_(polyak)
        t.data.add_((1 - polyak) * n.data)

    for t, n in zip(atarget.parameters(),anetwork.parameters()):
        t.data.mul_(polyak)
        t.data.add_((1 - polyak) * n.data)
    


def test_agent():
        num_test_episodes=10
        avg_score_test = []
        max_ep_len = 100000
        for j in range(num_test_episodes):
            o, d, ep_ret, ep_len = env.reset(), False, 0, 0
            g = o['desired_goal']
            o = o['observation']
            while not (d or (ep_len == max_ep_len)):
                # Take deterministic actions at test time (noise_2scale=0)
                env.render()
                newo = np.append(o,g)
                action = get_action(newo, 0)
                o, r, d, info = env.step(action)
                print(r,info,action)
                o = o['observation']
                ep_ret += r
                ep_len += 1
            avg_score_test.append(ep_ret)
        print(ep_ret)
   
if __name__ == '__main__':
    main()