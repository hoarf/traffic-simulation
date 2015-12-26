import os
from GA import GA
from QL import QL
from time import localtime
import KSP

SF_NETWORK_NAME = "SF"

class Driver():
    #od:OD = instance of OD class
    def __init__(self,OD):
        self.od = OD

    def od_s(self):
        return "%s%s" % (self.od.o, self.od.d)

class OD():
    #O:string = origin node
    #D:string = destination node
    #numPath: int = number of shortest paths to generate
    #numTravels: int = number of travels
    def __init__(self,O,D,numPaths,numTravels):
        self.o = O
        self.d = D
        self.numPaths = numPaths
        self.numTravels = numTravels
        self.paths = None

    def __str__(self):
        return "origin: " + str(self.o) + " destination: "+str(self.d) + \
                "number of travels: " + str(self.numTravels) + " number of shortest paths: " \
                + str(self.numPaths)

class Experiment:

    def __init__(self, k, networkFile, capacitiesFile, odFile, groupSize,
                 printTravelTime=False, printDriversPerLink=False,
                 printPairOD=False, printInterval=1):
        self.printDriversPerLink = printDriversPerLink
        self.printTravelTime = printTravelTime
        self.printPairOD= printPairOD
        self.printInterval = printInterval
        self.networkName = "OW10_1" if "OW10_1" in networkFile else SF_NETWORK_NAME
        self.networkSet = False
        self.edges = {}
        self.initializeNetworkData(k, networkFile, capacitiesFile, odFile, groupSize)

    def initializeNetworkData(self, k, networkFile, capacitiesFile, odFile, groupSize):

        self.networkSet = True
        self.k = k
        self.groupsize = groupSize
        odInput = self.parseODfile(odFile)
        self.ODlist = []

        for tupOD in odInput:
            if(tupOD[2]%self.groupsize!=0):
                print(tupOD[2])
                raise Exception("Error: number of travels is not a multiple of the group size \
                        origin: "+str(tupOD[0])+" destination: "+ str(tupOD[1]))
            else:
                #Origin,destination,number of paths, number of travels
                self.ODlist.append(OD(tupOD[0],tupOD[1],k,tupOD[2]/self.groupsize))

        if self.networkName == SF_NETWORK_NAME:
            print("Parsing capacity file: %s" % capacitiesFile)
            self.capacities = self.parseCapacityFile(capacitiesFile)

        #calculating k shortest routes for each OD pair
        V,E = KSP.generateGraph(networkFile)
        for od in self.ODlist:
            od.paths = KSP.getKRoutes(V, E, od.o, od.d, od.numPaths)

        ##get the value of each link - free flow travel time
        self.freeFlow={}
        for edge in E:
            self.freeFlow[edge.start+"|"+edge.end]=edge.length

        self.edgeNames = sorted(self.freeFlow.keys())

        self.edges = self.parseCapacityFile(networkFile)

        #creates different drivers according to the number of travels of each OD
        #instance
        self.drivers=[]
        for od in self.ODlist:
            for travel in range(od.numTravels):
                self.drivers.append(Driver(od))

    def parseODfile(self,path):
        with open(path) as odFILE:
            lines = odFILE.readlines()
        odList = []
        for line in lines:
            line = line.replace(' ', '').replace('\n','')
            items = line.split(',')
            if(len(items) == 3):
                odList.append((items[0],items[1],int(items[2])))
        return odList

    def parseCapacityFile(self, path):
        links = {}
        with open(path) as capFILE:
            lines = capFILE.readlines()
            for line in lines:
                line = line.replace('\n','')
                items = line.split(' ')
                if(len(items) == 4):
                    links[items[1]+"|"+items[2]] = float(items[3])
        return links

    def genCallBack(self,ga_engine):
        population = ga_engine.getPopulation()
        generation = ga_engine.getCurrentGeneration()

        #gets worst individual
        worstsol = population[len(population)-1]

        if (self.useQL == True): ##if using QL
            #check if the GA->QL interval is None
            if (self.interval == None):
                isGeneration = 1
            else:
                isGeneration = (generation+1) % self.interval

            #check if we are running the GA<->QL or GA<-QL experiment.
            if((self.useInterval) and (isGeneration == 0) and (generation != 0)):
                (qlind,avg_tt) = self.ql.runEpisodeWithAction(ga_engine.bestIndividual().getInternalList()) #GA<-QL
            else:
                (qlind,avg_tt) = self.ql.runEpisode() #GA<-QL
                #qlind is a array of paths taken by each driver

            #for each driver
            for i in range(len(qlind)):
                worstsol.getInternalList()[i] = qlind[i]
            worstsol.evaluate()

            #if worstscore has a smaller average travel time than the
            #best individual, copies the ql solution (worstscore)
            #to the second best individual
            if worstsol.score < ga_engine.bestIndividual().score:
                print(">>>>> QL indiv. "+ str(worstsol.score), "turned better than best ind. "+ str(ga_engine.bestIndividual().score)+ "at generation "+ str(generation))
                #copies QL solution to 2nd best ind.
                worstsol.copy(ga_engine.getPopulation()[1])
                ga_engine.getPopulation()[1].evaluate()
            else:
                #copies QL solution to worst in population
                worstsol.copy(ga_engine.getPopulation()[1])
                ga_engine.getPopulation()[len(population)-1].evaluate()

        self.__print_step(generation,ga_engine.bestIndividual().getInternalList(),avgTT=ga_engine.bestIndividual().score, qlTT=worstsol.score)

    def buildODPairData(self, ttByOD):
        """
        returns the string of OD pair data
        """
        str_od = ''

        for k in ttByOD.keys():
            str_od += " %4.4f" % (sum(ttByOD[k])/len(ttByOD[k]))

        return str_od + ' '

    def __print_step(self, stepNumber, stepSolution, avgTT=None, qlTT=None):
        if stepNumber % self.printInterval == 0:
            if(self.useGA):
                if(self.useQL):
                    self.outputFile.write(str(stepNumber)+" "+str(avgTT) +" "+ str(qlTT))
                else:
                    self.outputFile.write(str(stepNumber)+" "+str(avgTT))
            else:
                self.outputFile.write(str(stepNumber)+" "+ str(qlTT))

            if(self.printPairOD):
                ttByOD = self.travelTimeByOD(stepSolution)
                self.outputFile.write(self.buildODPairData(ttByOD))

            if(self.printTravelTime):
                travel_times = ''
                edges = self.calculateEdgesTravelTimes(stepSolution)
                for edge in self.edgeNames:
                    travel_times += str(edges[edge]) + " "
                self.outputFile.write(travel_times.strip())

            if(self.printDriversPerLink):
                drivers = ''
                edges = self.driversPerLink(stepSolution)
                for edge in self.edgeNames:
                    drivers += str(edges[edge]) + " "
                self.outputFile.write(drivers.strip())

            self.outputFile.write("\n")

    def nodesString(self):
        ##string of edges in graph that will be printed
        nodesString = ''
        if self.printPairOD:
            for od in self.ODlist:
                nodesString += "tt_%s|%s " % (od.o, od.d)
        if(self.printTravelTime):
            for edgeN in self.edgeNames:
                nodesString += 'tt_'+edgeN+' '
        if(self.printDriversPerLink):
            for edgeN in self.edgeNames:
                nodesString += "nd_"+edgeN+' '
        nodesString = nodesString.strip()
        return nodesString

    def nd(self):
        return len(self.drivers)*self.groupsize

    def appendTag(self, filenamewithtag):
        #tests if there isn't already a file with the desired name
        #paralellization of experiments may result in filename conflit
        append_number = ''
        while(os.path.isfile(filenamewithtag+append_number+".txt")):
            if(append_number == ''):
                append_number = "-1"
            else:
                append_number = "-"+str(int(append_number[1:])+1)
        filenamewithtag += append_number + ".txt"
        return filenamewithtag

    def createStringArgumentsQL(self, nd):
        """
        nd: number of drivers without groupsize
        """
        fmt = './results_gaql_grouped/net_%s/QL/decay%4.3f/alpha%3.2f'
        path2simulationfiles = fmt % (self.networkName, self.decay, self.alpha)

        filename = path2simulationfiles +  '/'+self.networkName \
                + '_k' + str(self.k) + '_a' + str(self.alpha) + '_d' + str(self.decay)\
                + '_'+ str(localtime()[3])+'h'+ str(localtime()[4])+'m'+ str(localtime()[5])+'s'

        headerstr = '#parameters:' + ' k=' + str(self.k) + ' alpha=' + str(self.alpha) \
                + ' decay=' + str(self.decay) + ' number of drivers=' + str(nd) \
                + ' groupsize= '+ str(self.groupsize)\
                + '\n#episode avg_tt ' + self.nodesString()

        return filename, path2simulationfiles, headerstr

    def createStringArguments(self, useQL, useInt):
        if(useQL and useInt):
            fmt = './results_gaql_grouped/net_%s/GA<->QL/pm%4.4f/decay%4.3f/alpha%3.2f/QL<-GA_Interval%s'
            path2simulationfiles = fmt % (self.networkName, self.mutation,
                                          self.decay, self.alpha, self.interval)

            filenamewithtag = path2simulationfiles +  '/net'+self.networkName + '_pm'\
                    + str(self.mutation) + '_c' + str(self.crossover) + '_e' + str(self.elite) \
                    + '_k' + str(self.k) + '_a' + str(self.alpha) + '_d' + str(self.decay)\
                    + '_nd'+ str(self.nd()) + '_groupsize'+ str(self.groupsize) \
                    + '_interval'+ str(self.interval) + '_' + str(localtime()[3])+'h'+ str(localtime()[4]) \
                    +'m'+ str(localtime()[5])+'s'

            headerstr = '#parameters: generations=' + str(self.generations) + ' pop.size='\
                    + str(self.population) + ' self.mutation=' + str(self.mutation) + ' crossover=' + str(self.crossover) \
                    + ' elit=' + str(self.elite) + ' k=' + str(self.k) + ' alpha=' + str(self.alpha) \
                    + ' decay=' + str(self.decay) + ' number of drivers=' + str(self.nd()) \
                    + ' groupsize= '+ str(self.groupsize) + ' GA->QL interval=' + str(self.interval)\
                    + '\n#generation avg_tt ql_avg_tt ' + self.nodesString()

        elif(useQL):
            fmt = './results_gaql_grouped/net_%s/GA<-QL/pm%4.4f/decay%4.3f/alpha%3.2f'
            path2simulationfiles = fmt % (self.networkName, self.mutation,
                                          self.decay, self.alpha)

            filenamewithtag = path2simulationfiles +  '/net'+self.networkName + '_pm'\
                    + str(self.mutation) + '_c' + str(self.crossover) + '_e' + str(self.elite) \
                    + '_k' + str(self.k) + '_a' + str(self.alpha) + '_d' + str(self.decay)\
                    + '_nd'+ str(self.nd()) + '_groupsize'+ str(self.groupsize) \
                    + '_'+ str(localtime()[3])+'h'+ str(localtime()[4])+'m'+ str(localtime()[5])+'s'

            headerstr = '#parameters: generations=' + str(self.generations) + ' pop.size='\
                    + str(self.population) + ' mutation=' + str(self.mutation) + ' crossover=' + str(self.crossover) \
                    + ' elit=' + str(self.elite) + ' k=' + str(self.k) + ' alpha=' + str(self.alpha) \
                    + ' decay=' + str(self.decay) + ' number of drivers=' + str(self.nd()) \
                    + ' groupsize= '+ str(self.groupsize) \
                    + '\n#generation avg_tt ql_avg_tt ' + self.nodesString()
        else:
            fmt = './results_gaql_grouped/net_%s/GA/pm%4.4f'
            path2simulationfiles = fmt % (self.networkName, self.mutation)

            filenamewithtag = path2simulationfiles +  '/net'+self.networkName + '_pm'\
                    + str(self.mutation) + '_c' + str(self.crossover) + '_e' + str(self.elite) \
                    + '_k' + str(self.k) \
                    + '_nd'+ str(self.nd()) + '_groupsize'+ str(self.groupsize) \
                    + '_'+ str(localtime()[3])+'h'+ str(localtime()[4])+'m'+ str(localtime()[5])+'s'

            headerstr = '#parameters: generations=' + str(self.generations) + ' pop.size='\
                    + str(self.population) + ' mutation=' + str(self.mutation) + ' crossover=' + str(self.crossover) \
                    + ' groupsize= '+ str(self.groupsize) + " k= "+str(self.k) \
                    + '\n#generation avg_tt ' +  self.nodesString()

        return filenamewithtag, path2simulationfiles, headerstr

    def run_ql(self, numEpisodes, alpha, decay):
        self.useGA = False
        self.useQL = True
        self.alpha = alpha
        self.decay = decay
        self.ql = QL(self, self.drivers, self.k, self.decay, self.alpha)

        filename, path2simulationfiles, headerstr = self.createStringArgumentsQL(len(self.drivers))
        filenamewithtag = self.appendTag(filename)

        if os.path.isdir(path2simulationfiles) == False:
            os.makedirs(path2simulationfiles)

        self.outputFile = open(filenamewithtag, 'w')
        self.outputFile.write(headerstr+'\n')

        for episode in range(numEpisodes):
            (instance, value) = self.ql.runEpisode()
            self.__print_step(episode,instance,qlTT=value)

        print("Output file location: %s" % filenamewithtag)

        self.outputFile.close()

    def run_ga_ql(self,useQL,useInt,generations, population, crossover, mutation, elite, alpha, decay,interval):
        self.useGA = True
        self.useQL = useQL
        self.useInterval = useInt
        self.interval = interval
        self.generations = generations
        self.population = population
        self.crossover = crossover
        self.mutation = mutation
        self.elite = elite
        self.alpha = alpha
        self.decay = decay
        if(useQL):
            self.ql = QL(self,self.drivers, self.k, self.decay,self.alpha)

        filename, path2simulationfiles, headerstr = self.createStringArguments(useQL, useInt)
        filenamewithtag = self.appendTag(filename)

        ##creates file
        if os.path.isdir(path2simulationfiles)==False:
            os.makedirs(path2simulationfiles)

        self.outputFile = open(filenamewithtag, 'w')
        self.outputFile.write(headerstr+'\n')

        self.ga = GA(generations, population, crossover, mutation, elite, self,
                     self.genCallBack, self.calculateAverageTravelTime,self.drivers)
        self.ga.evolve()

        print("Output file location: %s" % filenamewithtag)
        self.outputFile.close()

    def driversPerLink(self,driverString):
        """
        receives an array of ints stresenting the chosen path of each group
        the array is sorted in the same way as the alleles and the drivers
        list
        returns a dicionary where the keys are edges and the values are the
        amount of drivers on the edge
        """
        global drivers
        global freeFlow
        global groupsize
        dicti = {}
        for inx,dr in enumerate(driverString):
            if(type(dr) != int):
                print('problema!',driverString,'\n')
            path = self.drivers[inx].od.paths[dr]
            for edge in path[0]:
                if edge in dicti.keys():
                    dicti[edge] +=self.groupsize
                else:
                    dicti[edge] = self.groupsize
        for link in self.freeFlow.keys():
            if link not in dicti.keys():
                dicti[link]=0
        return dicti

    def evaluateActionTravelTime(self, driverIndex, action, edgesTravelTimes):
        #calculates travel times for a driver
        traveltime = 0.0
        path = self.drivers[driverIndex].od.paths[action][0] ##list of nodes of path
        for edge in path:
            traveltime += edgesTravelTimes[edge]
        return traveltime

    def initTravelTimeByODDict(self):
        d = {}
        for od in self.ODlist:
            d["%s%s" % (od.o, od.d)] = []
        return d

    def travelTimeByOD(self, stringOfActions):
        edgesTravelTimes = self.calculateEdgesTravelTimes(stringOfActions)
        odTravelTimeDict = self.initTravelTimeByODDict()

        for driverIdx, action in enumerate(stringOfActions):
            path = self.drivers[driverIdx].od.paths[action][0]
            traveltime = 0.0
            for edge in path:
                traveltime += edgesTravelTimes[edge]
            odTravelTimeDict[self.drivers[driverIdx].od_s()].append(traveltime)
        return odTravelTimeDict

    def calculateIndividualTravelTime(self, stringOfActions):
        #returns list of travel times for each driver
        edgesTravelTimes = self.calculateEdgesTravelTimes(stringOfActions)
        results = []
        for driverIdx, action in enumerate(stringOfActions):
            travel_times = self.evaluateActionTravelTime(driverIdx, action, edgesTravelTimes)
            results.append(travel_times)
        return results

    def calculateEdgesTravelTimes(self, stringOfActions):
        ###############################
        # TRAVEL TIME FUNCTION               #
        ###############################
        ##VDF TRAVEL TIME FUNCTION
        vdfAlpha = 0.15
        vdfBeta = 4
        #calculates travel time each edge
        edges_travel_times = {}
        ##flow
        linkOccupancy = self.driversPerLink(stringOfActions)
        for edge in self.freeFlow.keys():
          if self.networkName == SF_NETWORK_NAME:
              edges_travel_times[edge] = self.freeFlow[edge]*(1+vdfAlpha *((linkOccupancy[edge]/self.capacities[edge])**vdfBeta))
          else:
              edges_travel_times[edge] = self.freeFlow[edge] + .02*linkOccupancy[edge]
        return edges_travel_times

    def calculateAverageTravelTime(self,stringOfActions):
        return sum(self.calculateIndividualTravelTime(stringOfActions))/len(stringOfActions)
