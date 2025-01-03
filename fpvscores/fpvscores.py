import json
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy import inspect
import requests
import logging
from RHUI import UIField, UIFieldType, UIFieldSelectOption

class FPVScores():
    FPVS_VERSION = "2.0.0"
    FPVS_API_ENDPOINT = "https://api.fpvscores.com"
    FPVS_API_VERSION = "0.1.0"
    FPVS_UPDATE_REQ = False

    with open('plugins/fpvscores/static/assets/data/countries.json', 'r') as file:
        countries_data = json.load(file)
    options = []
    for country in countries_data:
        code = country["alpha2"]
        name = country["name"]
        option = UIFieldSelectOption(code, name)
        options.append(option)
    options.sort(key=lambda x: x.label)
    country_ui_field = UIField('country', "Country Code", UIFieldType.SELECT, options=options, value="")

    def __init__(self,rhapi):
        self.logger = logging.getLogger(__name__)
        self._rhapi = rhapi

    def init_plugin(self,args):
        isEnabled = self.isEnabled()
        isConnected = self.isConnected()
        notEmptyKeys = self.getEventUUID()["notempty"]

        if isEnabled is False:
            self.logger.warning("FPVScores.com Sync is disabled. Please enable on the Format page")
        elif notEmptyKeys is False:
            self.logger.warning("FPVScores.com Event UUID is empty. Please register at https://fpvscores.com")
        elif isConnected is False:
            self.logger.warning("It looks like your RotorHazard timer is not connected to the internet. Check connection and try again.")
        else:
            x = requests.get(self.FPVS_API_ENDPOINT+'/versioncheck.php?version='+self.FPVS_VERSION)
            respond = x.json()
            if self.FPVS_VERSION != respond["version"]:
                if respond["softupgrade"] == True:
                    self.logger.warning("New version of FPVScores.com Sync Plugin is available. Please consider upgrading.")

                if respond["forceupgrade"] == True:
                    self.logger.warning("FPVScores.com Sync Plugin needs to bee updated. ")
                    self.FPVS_UPDATE_REQ = True

            self.logger.info("FPVScores.com Sync is ready")
        
        self.init_ui(args)

    def init_ui(self,args):
        ui = self._rhapi.ui
        ui.register_panel("fpvscores_sync", "FPV Scores", "format")

        ui_fpvscores_autosync = UIField(name = 'fpvscores_autoupload', label = 'Enable Automatic Sync', field_type = UIFieldType.CHECKBOX, desc = "Enable or disable automatic syncing. A network connection is required.")
        ui_fpvscores_event_uuid = UIField(name = 'fpvscores_event_uuid', label = 'FPV Scores Event UUID', field_type = UIFieldType.TEXT, desc = "Event UUID obtainable from FPVScores.com")

        fields = self._rhapi.fields
        fields.register_option(ui_fpvscores_autosync, "fpvscores_sync")
        fields.register_option(ui_fpvscores_event_uuid, "fpvscores_sync")

        ui.register_quickbutton("fpvscores_sync", "fpvscores_syncpilots", "Full Manual Sync", self.runFullManualSyncBtn, {'rhapi': self._rhapi})
        ui.register_quickbutton("fpvscores_sync", "fpvscores_clear", "Clear event data on FPVScores.com", self.runClearBtn, {'rhapi': self._rhapi})

        fields.register_pilot_attribute( self.country_ui_field )
        fields.register_pilot_attribute( UIField('safetycheck', "Safety Checked", UIFieldType.CHECKBOX) )
        fields.register_pilot_attribute( UIField('fpvs_uuid', "FPVS Pilot UUID", UIFieldType.TEXT) )
        fields.register_pilot_attribute( UIField('comm_elrs', "ELRS Passphrase", UIFieldType.TEXT) )
        fields.register_pilot_attribute( UIField('comm_fusion', "Fusion Mac", UIFieldType.TEXT) )
        
        #ui.register_quickbutton("fpvscores_sync", "fpvscores_downloadavatars", "Download Pilot Avatars", self.runDownloadAvatarsBtn, {'rhapi': self._rhapi})

    def isConnected(self):
        try:
            response = requests.get(self.FPVS_API_ENDPOINT, timeout=5)
            return True
        except requests.ConnectionError:
            return False 
    
    def isEnabled(self):
        enabled = self._rhapi.db.option("fpvscores_autoupload")

        if enabled == "1" and self.FPVS_UPDATE_REQ == False:

            return True
        else:
            if self.FPVS_UPDATE_REQ == True:
                self.logger.warning("FPVScores requires a mandatory update. Please update and restart the timer. No results will be synced for now.")
            return False
        
    def getEventUUID(self):
        event_uuid = self._rhapi.db.option("fpvscores_event_uuid")
        notempty = True if (event_uuid) else False
        keys = {
            "notempty": notempty,
            "event_uuid": event_uuid,
        }
        return keys

    def class_listener(self,args):
        rhapi = self._rhapi
        
        keys = self.getEventUUID()
        if self.isConnected() and self.isEnabled() and keys["notempty"]:
            
            eventname = args["_eventName"]
            if eventname == "classAdd":
                classid = args["class_id"]
                classname = "Class " + str(classid)
                brackettype = "none"
                classdescription = "No description"

            elif eventname == "classAlter":
                classid = args["class_id"]
                raceclass = self._rhapi.db.raceclass_by_id(classid)
                classname = raceclass.name
                classdescription = raceclass.description
                brackettype = "check"

            elif eventname == "heatGenerate":
                classid = args["output_class_id"]
                raceclass = self._rhapi.db.raceclass_by_id(classid)
                if raceclass.name == "":
                    classname = "Class " + str(classid)
                else:
                    classname = raceclass.name
                classdescription = raceclass.description
                brackettype = self.get_brackettype(args)

            payload = {
                "event_uuid": keys["event_uuid"],
                "class_id": classid,
                "class_name": classname,
                "class_descr": classdescription,
                "class_bracket_type": brackettype,
                "event_name": eventname
            }
            x = requests.post(self.FPVS_API_ENDPOINT+"/rh/"+self.FPVS_API_VERSION+"/?action=class_update", json = payload)
            self.UI_Message(rhapi,x.text)


        else:
            self.logger.warning("FPVScores.com Sync Disabled")

    def get_brackettype(self,args):
        brackettype = args["generator"]      
        if brackettype == "Regulation_bracket__double_elimination" or brackettype == "Regulation_bracket__single_elimination":
            generate_args = args["generate_args"]
            brackettype = brackettype+"_"+generate_args["standard"]    
        return brackettype
    
    def UI_Message(self, rhapi, text):
        try:
            parsed_text = json.loads(text)
            # Controleer of het een lijst is en haal het eerste item
            if isinstance(parsed_text, list):
                parsed_text = parsed_text[0]

            # Controleer op "status" en "message" keys
            if "status" in parsed_text and "message" in parsed_text:
                if parsed_text["status"] == "error":
                    rhapi.ui.message_notify(rhapi.__("FPVScores: " + parsed_text["message"]))
                else:
                    rhapi.ui.message_notify(rhapi.__("FPVScores: " + parsed_text["message"]))
            else:
                rhapi.ui.message_notify(rhapi.__("FPVScores: Unexpected response format."))
        except json.JSONDecodeError:
            rhapi.ui.message_notify(rhapi.__("FPVScores: Failed to parse server response."))

    def heat_listener(self,args):
        rhapi = self._rhapi
        keys = self.getEventUUID()
        if self.isConnected() and self.isEnabled() and keys["notempty"]:

            db = self._rhapi.db
            heat = db.heat_by_id(args["heat_id"])
            groups = []
            thisheat = self.getGroupingDetails(heat,db)
            groups.append(thisheat)

            payload = {
                "event_uuid": keys["event_uuid"],
                "heats": groups
            }
            x = requests.post(self.FPVS_API_ENDPOINT+"/rh/"+self.FPVS_API_VERSION+"/?action=heat_update", json = payload)
            self.UI_Message(rhapi,x.text)


        else:
            self.logger.warning("FPVScores.com Sync Disabled")

    def class_delete(self,args):
        rhapi = self._rhapi
        keys = self.getEventUUID()
        if self.isConnected() and self.isEnabled() and keys["notempty"]:
            payload = {
                "event_uuid": keys["event_uuid"],
                "class_id": args["class_id"]
            }
            x = requests.post(self.FPVS_API_ENDPOINT+"/rh/"+self.FPVS_API_VERSION+"/?action=class_delete", json = payload)
            self.UI_Message(rhapi,x.text)
            #print(x.text)
        else:
            self.logger.warning("FPVScores.com Sync Disabled")

    def heat_delete(self,args):
        rhapi = self._rhapi
        keys = self.getEventUUID()
        if self.isConnected() and self.isEnabled() and keys["notempty"]:

            payload = {
                "event_uuid": keys["event_uuid"],
                "heat_id": args["heat_id"]
            }
            x = requests.post(self.FPVS_API_ENDPOINT+"/rh/"+self.FPVS_API_VERSION+"/?action=heat_delete", json = payload)
            self.UI_Message(rhapi,x.text)
            #print(x.text)
        else:
            self.logger.warning("FPVScores.com Sync Disabled")

    def pilot_listener(self,args):
        rhapi = self._rhapi
        keys = self.getEventUUID()
        if self.isConnected() and self.isEnabled() and keys["notempty"]:
            eventname = args["_eventName"]
            if eventname == "pilotAdd":
                pilotid = args["pilot_id"]
                pilot = self._rhapi.db.pilot_by_id(pilotid)
                callsign = pilot.callsign
                name = pilot.name
                team = pilot.team
                phonetic = pilot.phonetic
                fpvsuuid = rhapi.db.pilot_attribute_value(pilot.id, 'fpvs_uuid')
                country = rhapi.db.pilot_attribute_value(pilot.id, 'country')
                color = pilot.color
                
            elif eventname == "pilotAlter":
                pilotid = args["pilot_id"]
                pilot = self._rhapi.db.pilot_by_id(pilotid)
                callsign = pilot.callsign
                name = pilot.name
                team = pilot.team
                phonetic = pilot.phonetic
                fpvsuuid = rhapi.db.pilot_attribute_value(pilot.id, 'fpvs_uuid')
                country = rhapi.db.pilot_attribute_value(pilot.id, 'country')
                color = pilot.color


            payload = {
                "event_uuid": keys["event_uuid"],
                "pilot_id": pilotid,
                "callsign": callsign,
                "name": name,
                "team": team,
                "country": country,
                "fpvs_uuid": fpvsuuid,
                "phonetic": phonetic,
                "color": color,
                "event_name": eventname
            }
            x = requests.post(self.FPVS_API_ENDPOINT+"/rh/"+self.FPVS_API_VERSION+"/?action=pilot_update", json = payload)
            print(x.text)
            self.UI_Message(rhapi,x.text)

    def getGroupingDetails(self, heatobj, db):
        heatname = str(heatobj.name)
        heatid = str(heatobj.id)

        if heatname == "None" or heatname == "":
            heatname = "Heat " + heatid

        heatclassid = str(heatobj.class_id)
        racechannels = self.getRaceChannels()

        thisheat = {
            "class_id": heatclassid,
            "class_name": "unsupported",
            "class_descr": "unsupported",
            "class_bracket_type": "",
            "heat_name": heatname,
            "heat_id": heatid,
            "slots":[]
        }
        slots = db.slots_by_heat(heatid)

        
        for slot in slots:
            if slot.node_index is not None:
                channel = racechannels[slot.node_index] 
                pilotcallsign = "-"
                if slot.pilot_id != 0:               
                    pilot = db.pilot_by_id(slot.pilot_id)
                    pilotcallsign = pilot.callsign
                thisslot = {
                    "pilotid": slot.pilot_id,
                    "nodeindex": slot.node_index,
                    "channel": channel,
                    "callsign": pilotcallsign
                }

                if (thisslot["channel"] != "0" and thisslot["channel"] != "00"):
                    thisheat["slots"].append(thisslot)
        return thisheat
    



    def getRaceChannels(self):
        frequencies = self._rhapi.race.frequencyset.frequencies
        freq = json.loads(frequencies)
        bands = freq["b"]
        channels = freq["c"]
        racechannels = []
        for i, band in enumerate(bands):
            racechannel = "0"
            if str(band) == 'None':
                racechannels.insert(i,racechannel)
            else:
                channel = channels[i]
                racechannel = str(band) + str(channel)
                racechannels.insert(i,racechannel)
        
        return racechannels

    def runClearBtn(self,args):
        rhapi = self._rhapi
        keys = self.getEventUUID()
        payload = {
            "event_uuid": keys["event_uuid"],
        }
        x = requests.post(self.FPVS_API_ENDPOINT+"/rh/"+self.FPVS_API_VERSION+"/?action=rh_clear", json = payload)
        print(x.text)
        self.UI_Message(rhapi,x.text)

    def runFullManualSyncBtn(self,args):
        rhapi = self._rhapi
        data = rhapi.io.run_export('JSON_FPVScores_Upload')
        self.uploadToFPVS_frombtn(data)
         
    def uploadToFPVS_frombtn(self, input_data):
        rhapi = self._rhapi
        json_data =  input_data['data']
        url = self.FPVS_API_ENDPOINT+"/rh/"+self.FPVS_API_VERSION+"/?action=full_manual_import"
        headers = {'Authorization' : 'rhconnect', 'Accept' : 'application/json', 'Content-Type' : 'application/json'}
        r = requests.post(url, data=json_data, headers=headers)
        self.UI_Message(rhapi,r.text)
        print(r.text)

    def runDownloadAvatarsBtn(args):
        print('run download avatars by frontend button')


    def laptime_listener(self,args):
        rhapi = self._rhapi
        keys = self.getEventUUID()

        if self.isConnected() and self.isEnabled() and keys["notempty"]:

            raceid = args["race_id"]

            savedracemeta = self._rhapi.db.race_by_id(raceid)
            classid = savedracemeta.class_id
            heatid = savedracemeta.heat_id
            roundid = savedracemeta.round_id

            raceclass = self._rhapi.db.raceclass_by_id(classid)
            classname = raceclass.name

            raceresults = self._rhapi.db.race_results(raceid)
            primary_leaderboard = raceresults["meta"]["primary_leaderboard"]
            filteredraceresults = raceresults[primary_leaderboard]

            pilotruns = self._rhapi.db.pilotruns_by_race(raceid)

            pilotlaps = []
            for run in pilotruns:
                runid = run.id
                laps = self._rhapi.db.laps_by_pilotrun(runid)
                for lap in laps:

                    if lap.deleted == False:
                        thislap = {
                            "id": lap.id,
                            "race_id": lap.race_id,
                            "pilotrace_id": lap.pilotrace_id,
                            "pilot_id": lap.pilot_id,
                            "lap_time_stamp": lap.lap_time_stamp,
                            "lap_time": lap.lap_time,
                            "lap_time_formatted": lap.lap_time_formatted,
                            "deleted": 1 if lap.deleted else 0,
                            "node_index": lap.node_index
                        }
                        pilotlaps.append(thislap)

            payload = {
                "event_uuid": keys["event_uuid"],
                "raceid": raceid,
                "classid": classid,
                "classname": classname,
                "heatid": heatid,
                "roundid": roundid,
                "method_label": primary_leaderboard,
                "roundresults": filteredraceresults,
                "pilotlaps": pilotlaps
            }

            x = requests.post(self.FPVS_API_ENDPOINT+"/rh/"+self.FPVS_API_VERSION+"/?action=laptimes_update", json = payload)
            #print(x.text)
            self.UI_Message(rhapi,x.text)
            self.logger.info("Laps sent to cloud")


    def results_listener(self,args):
        
        rhapi = self._rhapi
        keys = self.getEventUUID()

        self.laptime_listener(args)
        savedracemeta = self._rhapi.db.race_by_id(args["race_id"])
        classid = savedracemeta.class_id
  
        raceclass = self._rhapi.db.raceclass_by_id(classid)
        classname = raceclass.name
        ranking = raceclass.ranking
        if self.isConnected() and self.isEnabled() and keys["notempty"]:

            rankpayload = []
            resultpayload = []

            if ranking != None:
                if isinstance(ranking, bool) and ranking is False:

                    rankpayload = []

                else:

                    meta = ranking["meta"]
                    method_label = meta["method_label"]
                    ranks = ranking["ranking"]

                    for rank in ranks:
                        # Specifieke waardes ophalen en verwijderen uit rank
                        rank_values = rank.copy()  # Maak een kopie om originele data niet te overschrijven

                        pilot_id = rank_values.pop("pilot_id", None)
                        callsign = rank_values.pop("callsign", None)
                        position = rank_values.pop("position", None)
                        team_name = rank_values.pop("team_name", None)
                        node = rank_values.pop("node", None)
                        total_time_laps = rank_values.pop("total_time_laps", None)

                        # heat = rank_values.pop("heat", None)  # Uncomment als 'heat' wordt gebruikt

                        # Maak het pilot-dict
                        pilot = {
                            "classid": classid,
                            "classname": classname,
                            "pilot_id": pilot_id,
                            "callsign": callsign,
                            "position": position,
                            "team_name": team_name,
                            "node": node,
                            # "heat": heat,  # Uncomment als 'heat' wordt gebruikt
                            "method_label": method_label,
                            "rank_fields": meta["rank_fields"],
                            "rank_values": rank_values,  # Hier blijven alleen de overgebleven waardes over
                        }

                        # Debug output (indien nodig)
                        print(pilot)

                        # Toevoegen aan rankpayload
                        rankpayload.append(pilot)    

            db = self._rhapi.db    
            fullresults = db.raceclass_results(classid)
            if fullresults is not None:
                meta = fullresults["meta"]
                leaderboards = ["by_consecutives", "by_race_time", "by_fastest_lap"]

                for leaderboard in leaderboards:
                    if leaderboard in fullresults:
                        for result in fullresults[leaderboard]:
                            pilot = {
                                "classid": classid,
                                "classname": classname,
                                "pilot_id": result["pilot_id"],
                                "callsign": result["callsign"],
                                "team": result["team_name"],
                                "node": result["node"],
                                "points": '',
                                "position": result["position"],
                                "consecutives": result["consecutives"],
                                "consecutives_base": result["consecutives_base"],
                                "laps": result["laps"],
                                "starts": result["starts"],
                                "total_time": result["total_time"],
                                "total_time_laps": result["total_time_laps"],
                                "last_lap": result["last_lap"],
                                "last_lap_raw": result["last_lap_raw"],
                                "average_lap": result["average_lap"],
                                "fastest_lap": result["fastest_lap"],
                                "fastest_lap_source_round": result.get("fastest_lap_source", {}).get("round", ''),
                                "consecutives_source_round": result.get("consecutives_source", {}).get("round", ''),
                                "total_time_raw": result["total_time_raw"],
                                "total_time_laps_raw": result["total_time_laps_raw"],
                                "average_lap_raw": result["average_lap_raw"],
                                "fastest_lap_source_heat": result.get("fastest_lap_source", {}).get("heat", ''),
                                "fastest_lap_source_displayname": result.get("fastest_lap_source", {}).get("displayname", ''),
                                "consecutives_source_heat": result.get("consecutives_source", {}).get("heat", ''),
                                "consecutives_source_displayname": result.get("consecutives_source", {}).get("displayname", ''),
                                "consecutives_lap_start": result.get("consecutive_lap_start", ''),
                                "method_label": leaderboard  # Noteer welk leaderboard gebruikt is
                            }
                            resultpayload.append(pilot)

                payload = {
                    "event_uuid": keys["event_uuid"],
                    "ranking": rankpayload,
                    "results": resultpayload,
                    "classid": classid
                }
                x = requests.post(self.FPVS_API_ENDPOINT+"/rh/"+self.FPVS_API_VERSION+"/?action=leaderboard_update", json = payload)
                print(x.text)
                self.UI_Message(rhapi,x.text)

                self.logger.info("Results sent to cloud")

            else:
                self.logger.info("No results available to resync")

        else:
            self.logger.warning("No internet connection available")



class AlchemyEncoder(json.JSONEncoder):
    def default(self, obj):
        custom_vars = [
            'fpvsuuid', 'country', 'node_frequency_band',
            'node_frequency_c', 'node_frequency_f', 'display_name'
        ]
        if isinstance(obj.__class__, DeclarativeMeta):
            # SQLAlchemy object
            mapped_instance = inspect(obj)
            fields = {}
            for field in mapped_instance.attrs.keys():
                try:
                    value = getattr(obj, field)
                    json.dumps(value)  # Test if serializable
                    fields[field] = value
                except TypeError:
                    fields[field] = None

            # Voeg alleen custom velden toe als ze bestaan op het object
            for custom_field in custom_vars:
                if hasattr(obj, custom_field):
                    fields[custom_field] = getattr(obj, custom_field, None)

            return fields
        return super().default(obj)