from utils.config import *
import time
import numpy as np
import math

class KinematicLegMotion:

    def __init__(self,LLp):
        self.rtime=time.time()
        self.running=False
        self.LLp=LLp

    def moveTo(self,newLLp,rtime,func=None):
        if self.running:
            print("Movement already running, please try again later.")
            return False
        self.startTime=time.time()
        self.startLLp=self.LLp
        self.func=func
        self.targetLLp=newLLp
        self.endTime=time.time()+rtime/1000
        self.running=True
        return True
    
    def update(self):
        diff=time.time()-self.startTime
        ldiff=self.targetLLp-self.startLLp
        tdiff=self.endTime-self.startTime
        ldiff/(tdiff*diff)
        p=1/tdiff*diff

        if time.time()>self.endTime and self.running:
            self.running=False
            p=1
        self.LLp=self.startLLp+ldiff*p
        if self.func:
            self.LLp=self.func(p,self.LLp)

    def step(self):
        if self.running:
            self.update()
        return self.LLp

class KinematicMotion:

    def __init__(self,Lp):
        self.Lp=Lp
        self.legs=[KinematicLegMotion(Lp[x]) for x in range(4)]

    def moveLegsTo(self,newLp,rtime):
        [self.legs[x].moveTo(newLp[x],rtime) for x in range(4)]

    def moveLegTo(self,leg,newLLp,rtime,func=None):
        return self.legs[leg].moveTo(newLLp,rtime,func)

    def step(self):
        return [x.step() for x in self.legs]


class TrottingGait:
    
    def __init__(self):
        self.step_gain = 0.8
        self.maxSl=2
        self.bodyPos=(0,100,0)
        self.bodyRot=(0,0,0)
        self.t0=300
        self.t1=1200
        self.t2=300
        self.t3=200
        self.Sl=0.0
        self.Sw=0
        self.Sh=STEP_HEIGHT
        self.Sa=0
        self.Spf=87
        self.Spr=77
        self.Fo=FORWARD_DISTANCE
        self.Ro=abs(BACKWARD_DISTANCE)

        self.Rc=[-50,0,0,1]
    def calcLeg(self,t,x,y,z):
        startLp=np.array([x-self.Sl/2.0,y,z-self.Sw,1])
        endY=0
        endLp=np.array([x+self.Sl/2,y+endY,z+self.Sw,1])
        
        if(t<self.t0):
            return startLp
        elif(t<self.t0+self.t1):

            td=t-self.t0
            tp=1/(self.t1/td)
            diffLp=endLp-startLp
            curLp=startLp+diffLp*tp
            psi=-((math.pi/180*self.Sa)/2)+(math.pi/180*self.Sa)*tp
            Ry = np.array([[np.cos(psi),0,np.sin(psi),0],
                    [0,1,0,0],
                    [-np.sin(psi),0,np.cos(psi),0],[0,0,0,1]])
            curLp=Ry.dot(curLp)
            return curLp
        elif(t<self.t0+self.t1+self.t2):
            return endLp
        elif(t<self.t0+self.t1+self.t2+self.t3):
            td=t-(self.t0+self.t1+self.t2)
            tp=1/(self.t3/td)
            diffLp=startLp-endLp
            curLp=endLp+diffLp*tp
            curLp[1]+=self.Sh*math.sin(math.pi*tp)
            return curLp
            
    def stepLength(self,len):
        self.Sl=len

    def positions(self,t,kb_offset={}):
        spf=self.Spf
        spr=self.Spr

        if list(kb_offset.values()) == [0.0, 0.0, 0.0]:
            self.Sl=0.0
            self.Sw=0.0
            self.Sa=0.0
        else:
            self.Sl=kb_offset['IDstepLength']
            self.Sw=kb_offset['IDstepWidth']
            self.Sa=kb_offset['IDstepAlpha']

        Tt=(self.t0+self.t1+self.t2+self.t3)
        Tt2=Tt/2
        rd=0
        td=(t*1000)%Tt
        t2=(t*1000-Tt2)%Tt
        rtd=(t*1000-rd)%Tt
        rt2=(t*1000-Tt2-rd)%Tt
        Fx=self.Fo
        Rx=-1*self.Ro
        Fy=-100
        Ry=-100
        r=np.array([self.calcLeg(td,Fx,Fy,spf),self.calcLeg(t2,Fx,Fy,-spf),self.calcLeg(rt2,Rx,Ry,spr),self.calcLeg(rtd,Rx,Ry,-spr)])
        return r
