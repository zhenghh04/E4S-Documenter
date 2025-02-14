#!/usr/bin/env python3

"""e4sListPage.py: Generates web pages listing e4s products from e4s_products.yaml"""
__author__ = "Wyatt Spear"

import urllib.request
from urllib.request import urlopen
import yaml
import subprocess
import datetime
import html
import sys
import os
import shutil
import re
from packaging.version import parse
import markdown
import base64
import json
import requests
import time
from datetime import datetime

timestamp='{:%Y-%m-%d %H:%M:%S}'.format(datetime.now())

script_path = os.path.dirname(os.path.abspath( __file__))
browserHeaders={'User-Agent' : "Magic Browser"}
rawSegment='/raw/'
blobSegment='/blob/'
srcSegment='/src/'
HEAD='HEAD'
e4sDotYaml='/e4s.yaml'
dotE4s='/.e4s'
bitbucketRaw='?&raw'
currentVersion='0.1.0'
github_uname="anonymous"
github_token="blank"
nameSet=set(())

printv=False #True
useRemoteYAML=True
printstandard=False #False
printstatus=False #True
htmlBlocks=""

def printV(toPrint):
    if printv is True:
        print(toPrint)
        

def printStandard(toPrint):
    if printstandard is True:
        print(toPrint)
        
def printStatus(toPrint):
    if printstatus is True:
        print(toPrint)

spackInfoTags=['Description','Homepage','Variants']
global noSpack
noSpack=False

def getSiteDeployment():
    site_file=script_path+'/../data/e4s_site_deployment.yaml'
    product_list={}
    with open(site_file, 'r') as sites:
        try:
            yamsites = yaml.safe_load(sites)
        except:
            printV("Couldn't get site deployment data.")
            return None
        else:
            #print(yamsites)
            for siteName,sysInfo in yamsites.items(): 
                #print(siteName)
                #print(sysInfo)
                for systemName,url in sysInfo:
                    #print(systemName)
                    #print(url)
                    siteBlob=getURLHead(url,0,-1)
                    #print(siteBlob)
                    siteBlob=siteBlob.splitlines()
                    #print(siteBlob)
                    for line in siteBlob[1:]:
                        #print(line)
                        if ',' in line: # and ",," not in line:
                            lineBlob=line.split(',')
                            #The patch entry in variants may have an arbitrary number of tokens so get the last entry from the end instead of counting up
                            lastDex=len(lineBlob)-1;
                            productName=lineBlob[0]
                            #if productName == "adios":
                            #    print(line)
                            if productName not in product_list.keys():
                                product_list[productName]={}
                            product=product_list[productName]
                            if siteName not in product.keys():
                                product[siteName]={}
                            site=product[siteName]
                            if systemName not in site.keys():
                                site[systemName]=[]
                            system=site[systemName]
                            
                            verDex=1
                            comDex=2
                            varDex=5
                            archDex=3
                            lastVar=lastDex

                            if lineBlob[4] != "linux" and lineBlob[4] != "cray":
                                varDex=3
                                #The last token might be hash, in which case the second to last is the architecture, which always has a '-'
                                if "-" not in lineBlob[lastDex]:
                                    lastDex=lastDex-1
                                archDex=lastDex
                                lastVar=archDex-1
                            varStep=varDex+1
                            while varStep <= lastVar:
                                lineBlob[varDex]=lineBlob[varDex]+","+lineBlob[varStep]
                                varStep=varStep+1
                            system.append([lineBlob[verDex],lineBlob[comDex],lineBlob[varDex],lineBlob[archDex]])
        return product_list 


def getCredentials():
    global github_uname
    global github_token
    with open(script_path+'/../credential.yaml', 'r') as cred:
        try:
            yamcred = yaml.safe_load(cred)
        except:
            printV("Couldn't get github credentials.")
            return None
        else:
            github_uname=yamcred["name"]
            github_token=yamcred["token"]

def getSpackInfo(name,accel):
    global noSpack
    infoMap={}
    if not noSpack:
        whichSpack = shutil.which('spack')
        if whichSpack is None:
            print("Spack not found in path. No Spack info data will be included")
            noSpack=True
            return None
    else:
        return None
    infoBlob = subprocess.run(['spack', 'info', name], stdout=subprocess.PIPE).stdout.decode('utf-8')
    if infoBlob is None or len(infoBlob)==0:
        printStandard("No spack info for "+name)
        printStatus(name+", False, "+accel+", False, False, False, False, False")
        return None
    rocmStatus=""
    cudaStatus=""
    syclStatus=""
    hipStatus=""
    hasTest="Absent"
    e4sTest="Absent"
    e4sTestSum="False"
    rocmSum="False"
    cudaSum="False"
    syclSum="False"
    testSum="False"
    hipSum="False"
    infoList=infoBlob.split("\n\n")
    for index,item in enumerate(infoList):
        for tag in spackInfoTags:
            if item.strip().startswith(tag):
                infoEntry=item.strip().split(':',1)
                value=infoEntry[1].strip(' \n')
                if tag == 'Homepage':
                    value=value.strip('/')
                    value="<a href="+value+">"+value+"</a>"
                if tag == 'Variants':
                    value=infoList[index+1]
                    variants=value.splitlines()
                    for line in variants:
                        if "rocm" in line:
                            rocmStatus="ROCM"
                            rocmSum="True"
                        if "cuda" in line: 
                            cudaStatus="CUDA"
                            cudaSum="True"
                        if "sycl" in line:
                            syclStatus="SYCL"
                            syclSum="True"
                        if "hip" in line:
                            hipStatus="HIP"
                            hipSum="True"
                    value=cudaStatus+" "+rocmStatus+" "+hipStatus+" "+syclStatus
                infoMap[infoEntry[0].strip(' \n')]=value
    packageLoc=subprocess.run(['spack', 'location', '-p', name], stdout=subprocess.PIPE).stdout.decode('utf-8').strip(' \n')
    packageLoc=packageLoc+"/package.py"
    with open(packageLoc,'r') as f:
        for line in f:
            if "def test(" in line:
                hasTest="Present"
                testSum="True"
    infoMap["Spack Smoke Test"]=hasTest
    testRes=os.system("bash -c \"grep -Ir spackLoadUnique ./testsuite/validation_tests/ | grep "+name+" &> /dev/null\"")
    if testRes == 0:
        e4sTest="Present"
        e4sTestSum="True"
    infoMap["E4S Testsuite Test"]=e4sTest
    printStatus(name+", True, "+accel+", "+cudaSum+", "+rocmSum+", "+hipSum+", "+syclSum+", "+testSum+", "+e4sTestSum)
    return infoMap

xGitDict={}
def getXGitlabID(url):
    global xGitDict
    url_split=url.split('/')
    base_url=url_split[0]+"//"+url_split[2]+"/"+url_split[3]+"/"+url_split[4]
    #Cache the id so we don't have to download the page for every file
    if base_url in xGitDict:
        return xGitDict[base_url]
    gid="Unknown"
    pidStr="Project ID: "
    response = requests.get(base_url)
    html = response.content.decode("utf-8")
    if not pidStr in html:
        xGitDict[base_url]=gid
        return gid
    piddex=html.index(pidStr)+len(pidStr)
    enddex=html.index("\n",piddex)
    gid=html[piddex:enddex]
    quotDex=gid.find("\"")
    if quotDex > -1:
        gid=gid[0:quotDex]
    #print("XGIT-ID: ",gid)
    xGitDict[base_url]=gid
    return gid

def parseRepoDate(dateStr):
    if(type(dateStr) is int):
        return datetime.fromtimestamp(dateStr/1000)
    else:
        #The last characters after the second differ, but for all known repos the date and time portion are the same and fixed length
        return datetime.strptime(dateStr[:19],"%Y-%m-%dT%H:%M:%S")

def getLastCommitDate(url):
    #Avoid api access rate limit errors. (There's probably a more efficient place to put this)
    
    if "github.com" in url:
       # print(url)
        url_split=url.split('/')
        #we need the first two tokens (repo and project) from the URL
        api_url="https://api.github.com/repos/"+url_split[3]+"/"+url_split[4]+"/commits?path="
        file_path=""
        for x in url_split[7:]:
            file_path=file_path+"/"+x
            #print(file_path)
        api_url=api_url+file_path+"&page=1&per_page=1"
        #print(api_url)
        try:
            #print(github_uname, github_token)
            json_url = requests.get(api_url,headers=browserHeaders,auth=(github_uname, github_token))
            data = json.loads(json_url.content)
            #time.sleep(60)
            #print (json_url)
            #print(str(data))
            #print(data.keys())
            #print(data["message"])
            if not data:
                print("Warning: Date information missing for: "+api_url) 
                return "Unknown"
            if "message" in data:
                print("Warning: Date information error")
                print(data["message"])
                return "Unknown"
            dateStr=data[0]["commit"]["committer"]["date"]
            #print("github date: "+dateStr)
            return parseRepoDate(dateStr)
            #return dateStr
        except urllib.error.HTTPError as e:
            print("Github API Fault: "+api_url)
            print(e.msg)
            print(e.hdrs)
            print(e.fp)
            #sys.exit(-1)
        print ("TIME DATA COLLECTION FAULT")
        return "Unknown"
    elif "bitbucket." in url:
        url_split=url.split('/')
        #we need the first two tokens (repo and project) from the URL
        api_url="https://api.bitbucket.org/2.0/repositories/"+url_split[3]+"/"+url_split[4]+"/commits?path="
        pathChunk=7
        customServer=False
        if "bitbucket.org" not in url:
            api_url="https://"+url_split[2]+"/rest/api/1.0/projects/"+url_split[4]+"/repos/"+url_split[6]+"/commits?path="
            #These url's will have another segment, so start after it
            pathChunk=8
            lastDex=len(url_split)-1
            if('?' in url_split[lastDex]):
                url_split[lastDex]=url_split[lastDex].split('?')[0]
            customServer=True
        file_path=""
        first=True
        for x in url_split[pathChunk:]:
            if first is True:
                first=False
            else:
                file_path=file_path+"/"
            file_path=file_path+x
        api_url=api_url+file_path+"&page=1&per_page=1"
        try:
            json_url = urlopen(api_url)
            data = json.loads(json_url.read())
            if customServer is True:
                dateStr=data["values"][0]["authorTimestamp"]
            else:    
                dateStr=data["values"][0]["date"]
            return parseRepoDate(dateStr)
        except urllib.error.HTTPError as e:
            print("API Commit Date Failure: Could not download: "+api_url)
            return "Unknown"
        except IndexError as e2:
            print("API Commit Date Failure: No commits at: "+api_url)
            return "Unknown"
        #print("bb date: "+dateStr)
        #return dateStr
    else:
        #We assume any other URL is xgitlab
        url_split=url.split('/')
        #we need the first two tokens (repo and project) from the URL
        gitlabid=getXGitlabID(url)
        if gitlabid == "Unknown":
            return "Unknown"
        #print("GITLABID: ",gitlabid)
        api_url="https://"+url_split[2]+"/api/v4/projects/"+gitlabid+"/repository/commits?path="
        
        file_path=""
        first=True
        for x in url_split[7:]:
            if first is True:
                first=False
            else:
                file_path=file_path+"/"
            file_path=file_path+x
        #print("BASE API URL: ", api_url)
        #print("FILE PATH: ", file_path)
        api_url=api_url+file_path+"&page=1&per_page=1"
        #print(api_url)
        json_url = urlopen(api_url)
        data = json.loads(json_url.read())
        #print(data[0]["committed_date"])
        dateStr=data[0]["committed_date"]
        #print("gitlab date: "+dateStr)
        return parseRepoDate(dateStr)

def getURLHead(url, skipChars=0, numChars=400):
    #masteryaml_url="https://raw.githubusercontent.com/UO-OACISS/e4s/master/docker-recipes/ubi7/x86_64/e4s/spack.yaml"
    #print("Reading URL: "+url)
    #browserHeaders={'User-Agent' : "Magic Browser"}
    req=urllib.request.Request(url,None,browserHeaders)
    #with urlopen(req) as f:
    try:
        f = urlopen(req)
        #Read 2x the target number of characters to look for a good breakpoint in the overflow
        if numChars > 0:
            head=html.escape(f.read(skipChars+(numChars*2)).decode("utf-8", errors='replace'))
        else:
            head=html.escape(f.read().decode("utf-8", errors='replace'))
        #Markdown comments don't count toward the character limit.
        if url.lower().endswith(".md"):
            comdex=head.rfind('\n[comment]:')
            if comdex > -1:
                noncomdex=head.find('\n',comdex+3)
                head=head[noncomdex:]
                head=head+html.escape(f.read(skipChars+(numChars*2)-len(head)).decode("utf-8"))
                #print(head)
                #print(len(head))
        if numChars > 0:
            head=head[skipChars:]
            breakpoint=head.find('\n',numChars)
            if breakpoint < numChars:
                breakpoint=head.find(". ",numChars)
            if breakpoint < numChars:
                breakpoint=head.find(' ',numChars);
            if breakpoint < numChars:
                breakpoint=numChars
            #print("Breakpoint: ",breakpoint)            
            head = head[:breakpoint]
            #print("Resulting Head: "+head)
        return head
    except urllib.error.URLError as e:
        print("ERROR: Document "+url+": "+e.reason)
        return None
    #    yamlMap=yaml.safe_load(url)
    #speclist = yamlMap.get('spack').get('specs')

def getRepoName(url, sub=False):
    if sub is True:
        name = os.path.basename(os.path.normpath(url))
        #print (name)
        return name
    #This means we have a github base repo url, not the raw blob path.
    if  url.count('/') == 4:
        lastslashdex=url.rfind('/')
        name=url[lastslashdex+1]
        print("Base github url name "+name)
        return name
    #print(url)
    lastblobdex=url.rfind('/blob/')
    if lastblobdex == -1:
        lastblobdex=url.rfind('/src/')
    if lastblobdex == -1:
        lastblobdex=url.rfind('/browse')  #Used in some bitbucket urls
    if lastblobdex == -1:
        print("ERROR PARSING REPO NAME FROM URL: "+url)
        return None
#    print("Name ends at: "+str(lastblobdex))
    firstnamedex=url.rfind('/',0,lastblobdex)
#    print("Name starts at: "+str(firstnamedex))
    name = url[firstnamedex+1:lastblobdex]
    #Some repos (gitlab) include an extra /-/ segment
    if name == "-":
        lastblobdex=url.rfind('/-/')
        firstnamedex=url.rfind('/',0,lastblobdex)
        name = url[firstnamedex+1:lastblobdex]
    return name

def readRemoteYaml(yaml_url,name):
    fromRaw="/blob/"
    toRaw="/raw/"
#                if 'raw_replace' in product:
#                    fromRaw=product['raw_replace'][0]
#                    toRaw=product['raw_replace'][1]
    if "bitbucket.org" in yaml_url:
        fromRaw="/src/"
    yaml_url = yaml_url.replace(fromRaw,toRaw)

    req=urllib.request.Request(yaml_url,None,browserHeaders)
    try:
        response=urlopen(req)
    except urllib.error.URLError as e:
        printV("Remote metadata for "+name+": "+e.reason+". "+yaml_url)
        return None
    else:
        try:
            yamlMD = yaml.safe_load(response)
        except:
            printV("Remote metadata for "+name+": Invalid yaml url. "+yaml_url)
            return None
        else:
            return yamlMD


def getRepoDocs(url,name,sub=False):
    yamlMD=None
    if useRemoteYAML is True:
        if sub is False:
            #TODO: This should work for github blob urls but may not work for others
            li = url.rsplit(blobSegment, 1)
            raw_url=rawSegment.join(li)
        else:
            raw_url=url
        #Check the hidden .e4s directory for e4s.yaml first
        raw_yaml_url=raw_url+dotE4s+e4sDotYaml
        yamlMD=readRemoteYaml(raw_yaml_url,name)
        if yamlMD is not None:
            printV("Found .e4s directory for "+name+" at "+raw_yaml_url)
            return yamlMD
    
        #print("Raw URL: "+raw_url)
        raw_yaml_url=raw_url+e4sDotYaml
        #print("Raw E4S "+raw_e4s)
        yamlMD=readRemoteYaml(raw_yaml_url,name)
    
        if yamlMD is not None:
            printV("Found top-level e4s.yaml for "+name)
            return yamlMD
    localFile=script_path+'/../data/'+name+e4sDotYaml
    if os.path.isfile(localFile) is True:
        with open(script_path+'/../data/'+name+e4sDotYaml) as MDFile:
            yamlMD = yaml.safe_load(MDFile)
            printV("Found local e4s.yaml for "+name)
            return yamlMD
    print("WARNING: No metadata found for "+name)
    return yamlMD #[{"e4s_product":name,"docs":[]}];
            
def processURL(url,sub=False):
    repoName=getRepoName(url,sub)
    if repoName in nameSet:
        print("ERROR. Duplicate repo name: "+repoName+" Skipping!")
    if repoName is None or repoName in nameSet:
        return None
    nameSet.add(repoName)
    yamlMD=getRepoDocs(url,repoName,sub)
    if yamlMD is not None and 'repo_url' not in yamlMD:
        yamlMD[0]['repo_url']=url
    if yamlMD is not None and 'version' in yamlMD[0]:
                repoVersion=yamlMD[0]['version']
                if parse(repoVersion) > parse(currentVersion):
                    print("Warning: using metadata version ("+repoVersion+") newer than supported version ("+currentVersion+").")
    return yamlMD #{'e4s_product':repoName,'docs':docs}

yamlEntryOpen='''{
    "name": "***CAPNAME***",
    "area": "***AREA***",
    "description": "***DESCRIPTION***",'''


def getDeploymentBlock(deployment):
    depAgg="<hr><details><summary><h3>Product Deployment</h3></summary><br><ul>"
    for sitePair in deployment.items():
        depAgg+="<li>"+sitePair[0]+"</li><ul>"
        for systemPair in sitePair[1].items():
            depAgg+="<li>"+systemPair[0]+"</li><ul>"
            for deps in systemPair[1]:
                depAgg+="<li><b>Version: </b>"+deps[0]+" <b>Compiler: </b>"+deps[1]+" <b>Variants: </b>"+deps[2]+" <b>Architecture: </b>"+deps[3]+"</li>"
            depAgg+="</ul>"
        depAgg+="</ul>"
    depAgg+="</ul></details>"
    #print(depAgg)
    return depAgg

def getDeploymentTable(deployment,name):
    depAgg="|Institution | E4S Deployment | Product | Version | Compiler | Variants | Architecture |\n" # Hash|\n"
    depAgg+="---| --- | --- | ---| --- | ---| --- |\n" # ---|\n"
    for sitePair in deployment.items():
        instname=sitePair[0]+" | "
        for systemPair in sitePair[1].items():
            sysname=systemPair[0]+" | "
            for deps in systemPair[1]:
                #if deps[3] == "linux" or deps[3] == "cray":
                    #print(deps)
                 #   depAgg+=instname+sysname+name+" | "+deps[0]+" | "+deps[1]+" | "+deps[4]+" | "+deps[2]+"\n"
                #depAgg+="<li><b>Version: </b>"+deps[0]+" <b>Compiler: </b>"+deps[1]+" <b>Variants: </b>"+deps[2]+" <b>Architecture: </b>"+deps[3]+"</li>"
                #else:
                depAgg+="|"+instname+sysname+name+" | "+deps[0]+" | "+deps[1]+" | "+deps[2]+" | "+deps[3]+"|\n" #" | HASH"+"\n"
    return depAgg

def getDeploymentYaml(deployment,name):
    
    depAgg="" # ---|\n"
    firstIt=True
    newBlock="{\n"
    for sitePair in deployment.items():
        instname="\"Institution\": \""+sitePair[0]+"\",\n"
        for systemPair in sitePair[1].items():
            sysname="\"E4S Deployment\": \""+systemPair[0]+"\",\n"
            for deps in systemPair[1]:
                #if deps[3] == "linux" or deps[3] == "cray":
                    #print(deps)
                 #   depAgg+=instname+sysname+name+" | "+deps[0]+" | "+deps[1]+" | "+deps[4]+" | "+deps[2]+"\n"
                #depAgg+="<li><b>Version: </b>"+deps[0]+" <b>Compiler: </b>"+deps[1]+" <b>Variants: </b>"+deps[2]+" <b>Architecture: </b>"+deps[3]+"</li>"
                #else:
                depAgg+=newBlock
                if firstIt:
                    newBlock=",\n{\n"
                    firstIt=False
                deps[2]=deps[2].replace("~"," ~")
                deps[2]=deps[2].replace("+"," +")
                deps[2]=deps[2].replace(","," ,")
                depAgg+=instname+sysname+"\"Product\": \""+name+"\",\n\"Version\": \""+deps[0]+"\",\n\"Compiler\": \""+deps[1]+"\",\n\"Variants\": \""+deps[2]+"\",\n\"Architecture\": \""+deps[3]+"\"\n}" #" | HASH"+"\n"
    return depAgg

def getPolicyStatusString(val):
    if val == 0:
        return "Unreported"
    if val == 1:
        return "Incomplete"
    if val == 2:
        return "Complete"
def getCompatibilityBlock(compat):
    totComp=0
    numPolicies=9
    explain="No explanation of policy compatability provided."
    policies=["Spack-based Build and Installation","Minimal Validation","Sustainability","Documentation","Product Metadata","Public Repository","Imported Software","Error Handling","Test Suite"]
    compAgg="<hr><details><summary><h3>E4S Policy Compatability</h3></summary><br><b>Overall Status:</b> "+getPolicyStatusString(totComp)+"<br><ol>"
    for policy in policies:
        compAgg+="<li><b>"+policy+": </b>"+getPolicyStatusString(totComp)+"<br><b>Note: </b>"+explain+"</li>"
    compAgg+="</ol></details>"
    return compAgg

def printDeployment(product,deployments,printYaml=True,firstBlock=False):
    capName=product['e4s_product'].upper()
    lowName=capName.lower()
    spackName=lowName
    if 'spack_name' in product:
        spackName=product['spack_name']

    printStandard("Printing deployment for: "+spackName)
    #print("FIRST BLOCK?! "+str(firstBlock))
    if type(deployments) is dict and spackName in deployments.keys():
        printV("Checking deployment for "+spackName)
        deployment=deployments[spackName]
        #htmlAgregator+=getDeploymentBlock(deployment)
        if printYaml:
            if not firstBlock:
                print(",", file=listPage)
            print(getDeploymentYaml(deployment,spackName), file=listPage)
        else:
            print(getDeploymentTable(deployment,spackName))
    else:
        printStandard("No deployment info for "+spackName)

    
def printProduct(product, ppage, deployments,sub=False, printYaml=False):
    #with open(output_prefix+product['e4s_product'].lower()+".html", "a") as ppage:
    capName=product['e4s_product'].upper()
    lowName=capName.lower()
    member=""
    if 'MemberProduct' in product and product['MemberProduct'] is True:
        capName=capName+"*"
    area="N/A"
    accel="Undetermined"
    accelArg="Undetermined"
    description=""
    if 'Area' in product:
        area=product['Area']
    elif 'area' in product:
        area=product['area']
    if 'Description' in product:
        description=product['Description']
    elif 'description' in product:
        description=product['description']
    if 'Accelerable' in product:
        if product['Accelerable'] is True:
            accel="Product provides spack variants to enable accelerator support"
            accelArg="True"
        elif product['Accelerable'] is False:
            accel="Product does not provide spack variants to enable accelerator support"
            accelArg="False"

    firstBlock=htmlBlocks['introLinkBlock']
    if printYaml is True:
        firstBlock=yamlEntryOpen
    print(firstBlock.replace("***CAPNAME***",capName).replace("***LOWNAME***", lowName).replace("***AREA***",area).replace("***DESCRIPTION***",description), file=listPage)

    htmlAgregator="";
    spackName=lowName
    if 'spack_name' in product:
        spackName=product['spack_name']
    spackInfo = getSpackInfo(spackName,accelArg)
    if spackInfo is not None:
        for key,value in spackInfo.items():
            printKey=key
            if key == "Variants":
                printKey="Accelerator Variants"
                htmlAgregator+="<B>Accelerator Support:</B> \n"+accel+"<br>\n"
            htmlAgregator+="<B>"+printKey+":</B> \n"+value+"<br>\n"
            #print("<B>"+key+":</B> \n"+value+"<br>\n",file=listPage)

    appendRaw=""
    rawFileURL = product['repo_url']
    #print("RFW "+rawFileURL)
    htmlAgregator+="<hr><h3>Document Summaries</h3><br>"
    #print("<hr><h3>Document Summaries</h3><br>",file=listPage)
    if sub is False:
        if 'raw_url' in product:
            rawFileURL = product['raw_url']
        
        if 'bitbucket.' in rawFileURL and '/browse' in rawFileURL:
            appendRaw=bitbucketRaw
            #rawFileURL = product['repo_url']
        else:
            fromRaw="/blob/"
            toRaw="/raw/"
#                if 'raw_replace' in product:
#                    fromRaw=product['raw_replace'][0]
#                    toRaw=product['raw_replace'][1]
            if "bitbucket.org" in rawFileURL:
                fromRaw="/src/"
            rawFileURL = rawFileURL.replace(fromRaw,toRaw)
   # print(rawFileURL)
    latestDocDate="Unknown"
    docKey='docs'
    if 'Docs' in product:
        docKey='Docs'
    for doc in product[docKey]:
        docLoc=""
        chars=400;
        skip=0
        if isinstance(doc,str):
            docLoc=doc
        else:
            if "doc" not in doc:
                print("ERROR! INVALID DOCUMENT MAP: "+str(doc))
                continue
            docLoc=doc["doc"]
            if "chars" in doc:
                chars=doc["chars"]
            if "skip" in doc:
                skip=doc["skip"]
        docURL=rawFileURL+"/"+docLoc+appendRaw
       # print(docURL)
        docHead=getURLHead(docURL,skip,chars)
        
        if docHead is None:
            continue
        docDate=getLastCommitDate(docURL)
        if not isinstance(docDate,str):
            if isinstance(latestDocDate,str) or docDate > latestDocDate:
                latestDocDate=docDate
        if docURL.lower().endswith(".md"):
            docHead=markdown.markdown(docHead)
        docLink="<a href="+product['repo_url']+"/"+docLoc+">"+docLoc+"</a>"
        docFix = htmlBlocks['docBlock'].replace("***DOCNAME***",docLink).replace("***DOCTEXT***",docHead).replace("***DOCURL***",product['repo_url']+"/"+docLoc).replace("***TIMESTAMP***",str(docDate))
        htmlAgregator+=docFix
        #print(docFix, file=ppage)
    #.replace('***DESCRIPTION***',"N/A").replace("***SITEADDRESS***","N/A").replace("***SPACKVERSION***","N/A")

    linkKey='links'
    if 'Links' in product:
        linkKey='Links'
    if linkKey in product:
        for link in product[linkKey]:
            linkLink="<a href="+link+">"+link+"</a><br>"

    #Make sure we got a valid dictionary from the deployment operation and that the current product is included.
    if type(deployments) is dict and spackName in deployments.keys():
        printV("Checking deployment for "+spackName)
        deployment=deployments[spackName]
        htmlAgregator+=getDeploymentBlock(deployment)
        #print(getDeploymentBlock(deployment))
    else:
        printV("No deployment info for "+spackName) 
       # printV(deployments.keys())

#    cBlock=getCompatibilityBlock(True)
    #print(cBlock)
#    htmlAgregator+=cBlock

    if printYaml is True:
        encodedBytes = base64.b64encode(htmlAgregator.encode("utf-8"))
        encodedStr = str(encodedBytes, "utf-8")
        print('''"html_blob": "'''+encodedStr+'''",''', file=ppage)
        print('''"last_updated": "'''+str(latestDocDate)+'''"}''', file=ppage)
        #print(yamlEntryClose, file=ppage)
    else:
        print(htmlAgregator, file=ppage)
        print(htmlBlocks['endBlock'], file=ppage)

def parse_html_blocks(templateLoc):
    with open(templateLoc,"r") as templateFile:
        blockText=templateFile.read()
    items = [item.strip() for item in re.split(r'<!--===|===-->',blockText)]
    return dict(zip(items[1::2], items[2::2]))

#To support repo urls without their default branch we need to add HEAD as appropriate to the repo site
def headify_url(baseURL):
    #If src or blob is present the url already includes the full path to the default branch
    if baseURL.find("/src/")>0 or baseURL.find("/blob/")>0:
        return baseURL
    
    if baseURL.find("github.com") >0 or baseURL.find("gitlab") >0:
        baseURL=baseURL+blobSegment+HEAD
        return baseURL
    
    if baseURL.find("bitbucket.org") >0:
        baseURL=baseURL+srcSegment+HEAD
        return baseURL
        
    print("WARNING: Could not headify "+baseURL)
    return baseURL

output_prefix=""
if(len(sys.argv)>1):
	if(os.path.isdir(sys.argv[1])):
		output_prefix=sys.argv[1]+"/"
	else:
		print("First argument must be a valid output directory")
		sys.exit(-1)

productList=script_path+'/../data/e4s_products.yaml'
if(len(sys.argv)>2):
	if(os.path.isfile(sys.argv[2])):
		productList=sys.argv[2]
	else:
		print("Second argument, if specified, must be a valid yaml product list")
		sys.exit(-1)
		
htmlTemplate=script_path+'/../templates/e4s_DocPortal_template.html'
templateFlag='--template'
printYaml=True
printDeployments=False
if(len(sys.argv)>3):
    if templateFlag in sys.argv:
        templateDex=sys.argv.index(templateFlag)
        templateLoc=sys.argv[templateDex+1]
        if(os.path.isfile(templateLoc)):
            htmlTemplate=templateLoc
        else:
            print("Third argument, if specified, must be a valid html output template")
            sys.exit(-1)
    
    if '--yaml' in sys.argv:
        printYaml=True
    if '--html' in sys.argv:
        printYaml=False
    if '--noRemote' in sys.argv:
        useRemoteYAML=False
    if '--deployments' in sys.argv:
        printDeployments=True
        printStandard("Printing deployments!")

if not printDeployments:
    printStatus("Product, Spack Package, Accelerable, CUDA Variant, ROCM Variant, HIP Variant, SYCL Variant, Smoke Test, Testsuite Test")

    htmlBlocks=parse_html_blocks(htmlTemplate)
    #print(htmlBlocks)
    getCredentials()
deployments=getSiteDeployment()

with open(productList) as MDlist:
    products = yaml.safe_load(MDlist)

listFileName="DocPortal"
if printDeployments:
    listFileName="E4S-Deployments"
listFileSuffix='.html'
yamlStart='''{
  "data": ['''
yamlEnd='''  ]
}'''
firstDepBlock=True
if printYaml is True:
    listFileSuffix='.yml'
with open(output_prefix+listFileName+listFileSuffix, "w") as listPage:
    if printYaml is True:
        print(yamlStart, file=listPage)
    else:
        print(htmlBlocks['introListBlock'].replace("***TIMESTAMP***",timestamp), file=listPage)

    firstIt = True
    for urls in products:
        if 'repo_url' not in urls:
            if 'version' in urls:
                repoVersion=urls['version']
                if parse(repoVersion) > parse(currentVersion):
                    print("Warning: using repo list version ("+repoVersion+") newer than supported version ("+currentVersion+").")
            continue
        baseURL=urls['repo_url']
        #print(baseURL)
        urls['repo_url']=headify_url(baseURL.rstrip('/'))
        printStandard("headified "+urls['repo_url'])
        processedURL=processURL(urls['repo_url'])
        if processedURL is None:
            print("Error: Could not process "+urls['repo_url'])
            continue
        printV(processedURL[0])
        product = processedURL[0]
        printStandard ('Generating HTML for: '+product['e4s_product'])
        if printYaml:
            if firstIt is True:
                firstIt=False
            elif not printDeployments:
                print(''',''', file=listPage)
        if printDeployments is True:
            printDeployment(product,deployments,printYaml=printYaml,firstBlock=firstDepBlock)
            firstDepBlock=False
        else:
            printProduct(product, listPage,deployments, printYaml=printYaml)
        if 'subrepo_urls' in product:
            for suburl in product['subrepo_urls']:
                printStandard("Generating HTML for SUBURL: "+suburl)
                processedURL=processURL(suburl,True)
                if processedURL is None:
                    continue
                if printYaml and not printDeployments:
                    print(''',''', file=listPage)
                product = processedURL[0]
                #print(product)
                if printDeployments:
                    printDeployment(product,deployments,printYaml=printYaml)
                else:
                    printProduct(product, listPage,True, printYaml=printYaml)
    if printYaml is True:
        print('''  ]
}''', file=listPage)
    else:
        print(htmlBlocks['introCloseBlock'].replace("***TIMESTAMP***",timestamp), file=listPage)
