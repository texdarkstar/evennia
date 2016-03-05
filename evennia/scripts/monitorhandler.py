"""
Monitors - catch changes to model fields and Attributes.

The MONITOR_HANDLER singleton from this module offers the following
functionality:

- Field-monitor - track a object's specific database field and perform
    an action whenever that field *changes* for whatever reason.
- Attribute-monitor tracks an object's specific Attribute and perform
    an action whenever that Attribute *changes* for whatever reason.

"""
from builtins import object

from collections import defaultdict
from evennia.server.models import ServerConfig
from evennia.utils.dbserialize import dbserialize, dbunserialize
from evennia.utils import logger

_SA = object.__setattr__
_GA = object.__getattribute__
_DA = object.__delattr__


class MonitorHandler(object):
    """
    This is a resource singleton that allows for registering
    callbacks for when a field or Attribute is updated (saved).
    """
    def __init__(self):
        """
        Initialize the handler.
        """
        self.savekey = "_monitorhandler_save"
        self.monitors = defaultdict(lambda:defaultdict(dict))

    def at_update(self, obj, fieldname):
        """
        Called by the field as it saves.
        """
        to_delete = []
        if obj in self.monitors and fieldname in self.monitors[obj]:
            for (callback, kwargs) in self.monitors[obj][fieldname].iteritems():
                kwargs.update({"obj": obj, "fieldname": fieldname})
                try:
                    callback( **kwargs)
                except Exception:
                    to_delete.append((obj, fieldname, callback))
                    logger.log_trace("Monitor callback was removed.")
            # we need to do the cleanup after loop has finished
            for (obj, fieldname, callback) in to_delete:
                del self.monitors[obj][fieldname][callback]

    def add(self, obj, fieldname, callback, **kwargs):
        """
        Add monitoring to a given field or Attribute. A field must
        be specified with the full db_* name or it will be assumed
        to be an Attribute (so `db_key`, not just `key`).

        Args:
            obj (Typeclassed Entity): The entity on which to monitor a
                field or Attribute.
            fieldname (str): Name of field (db_*) or Attribute to monitor.
            callback (callable): A callable on the form `callable(obj,
                fieldname, **kwargs), where kwargs holds keys fieldname
                and obj.
            uid (hashable): A unique id to identify this particular monitor.
                It is used together with obj to
            persistent (bool): If this monitor should survive a server
                reboot or not (it will always survive a reload).

        """
        if not fieldname.startswith("db_") or not hasattr(obj, fieldname):
            # an Attribute - we track it's db_value field
            obj = obj.attributes.get(fieldname, return_obj=True)
            if not obj:
                return
            fieldname = "db_value"

        # we try to serialize this data to test it's valid. Otherwise we won't accept it.
        try:
            dbserialize((obj, fieldname, callback, kwargs))
        except Exception:
            err = "Invalid monitor definition (skipped since it could not be serialized):\n" \
                  " (%s, %s, %s, %s)" % (obj, fieldname, callback, kwargs)
            logger.log_trace(err)
        else:
            self.monitors[obj][fieldname][callback] = kwargs


    def remove(self, obj, fieldname, callback):
        """
        Remove a monitor.
        """
        callback_dict = self.monitors[obj][fieldname]
        if callback in callback_dict:
            del callback_dict[callback]

    def save(self):
        """
        Store our monitors to the database. This is called
        by the server process.

        Since dbserialize can't handle defaultdicts, we convert to an
        intermediary save format ((obj,fieldname, callback, kwargs), ...)

        """
        savedata = []
        for obj in self.monitors:
            for fieldname in self.monitors[obj]:
                for callback in self.monitors[obj][fieldname]:
                    savedata.append((obj, fieldname, callback, self.monitors[obj][fieldname][callback]))
        savedata = dbserialize(savedata)
        ServerConfig.objects.conf(key=self.savekey,
                                  value=savedata)

    def restore(self):
        """
        Restore our monitors after a reload. This is called
        by the server process.
        """
        savedata = ServerConfig.objects.conf(key=self.savekey)
        if savedata:
            for (obj, fieldname, callback, kwargs) in dbunserialize(savedata):
                self.monitors[obj][fieldname][callback] = kwargs
            ServerConfig.objects.conf(key=self.savekey, delete=True)

##
## TrackerHandler is assigned to objects that should notify themselves to
## the OOB system when some property changes. This is never assigned manually
## but automatically through the OOBHandler.
##
#
#class _FieldMonitor(object):
#    """
#    This object will be stored on the tracked object as
#    "_oob_at_<fieldname>_postsave".  the update() method will be
#    called by the save mechanism, which in turn will call the
#    user-customizable func().
#
#    """
#    def __init__(self, obj, fieldname):
#        """
#        This initializes the monitor with the object it sits on.
#
#        Args:
#            obj (Object): Object handler is defined on.
#            fieldname (str): The name of the field to monitor
#
#        """
#        self.obj = obj
#        self.fieldname = fieldname
#        self.subscribers = defaultdict(list)
#
#    def __call__(self):
#        """
#        Called by the save() mechanism when the given field has
#        updated (it's already saved at this point).
#
#        Args:
#            fieldname (str): The field to monitor
#
#        """
#        global _SESSIONS
#        if not _SESSIONS:
#            from evennia.server.sessionhandler import SESSIONS as _SESSIONS
#
#        for sessid, functuples in self.subscribers.items():
#            # oobtuples is a list [(oobfuncname, args, kwargs), ...],
#            # a potential list of oob commands to call when this
#            # field changes.
#            session = _SESSIONS.get(sessid)
#            if session:
#                for (args, kwargs) in functuples:
#                    self.at_update(session, *args, **kwargs)
#
#    def add(self, session, *args, **kwargs):
#        """
#        Add a specific tracking callback to monitor
#
#        Args:
#            session (int): Session.
#            oobfuncname (str): oob command to call when field updates
#            args,kwargs (any): arguments to pass to oob commjand
#
#        Notes:
#            Each sessid may have a list of (oobfuncname, args, kwargs)
#            tuples, all of which will be executed when the
#            field updates.
#
#        """
#        self.subscribers[session.sessid].append((args, kwargs))
#
#    def remove(self, session):
#        """
#        Remove a subscribing session from the monitor
#
#        Args:
#            sessid(int): Session id
#
#        """
#        self.subscribers.pop(session.sessid, None)
#
#    def at_update(self, session, *args, **kwargs):
#        """
#        This should be overloaded for the respective functionality.
#        """
#        pass
#
#
#class _Repeater(object):
#    """
#    This object is created and used by the `OOBHandler.repeat` method.
#    It will be assigned to a target object as a custom variable, e.g.:
#
#    `obj._oob_ECHO_every_20s_for_sessid_1 = AtRepater()`
#
#    It will be called every interval seconds by the OOBHandler,
#    triggering whatever OOB function it is set to use.
#
#    """
#
#    def __call__(self, *args, **kwargs):
#        "Called at regular intervals. Calls the oob function"
#        INPUT_HANDLER.execute_cmd(kwargs["_sessid"], kwargs["_oobfuncname"], *args, **kwargs)
#
## Main OOB Handler
#
#class MonitorHandler(TickerHandler):
#    """
#    The MonitorHandler manages the monitoring of changes on Objects,
#    as requested by various agents (normally inputfuncs).
#    """
#
#    def __init__(self, *args, **kwargs):
#        """
#        Setup the tickerhandler wrapper.
#        """
#        super(OOBHandler, self).__init__(*args, **kwargs)
#        self.save_name = "oob_ticker_storage"
#        self.oob_save_name = "oob_monitor_storage"
#        self.oob_monitor_storage = {}
#
#    def _get_repeater_hook_name(self, oobfuncname, interval, sessid):
#        """
#        Get the unique repeater call hook name for this object
#
#        Args:
#            oobfuncname (str): OOB function to retrieve
#            interval (int): Repeat interval
#            sessid (int): The Session id.
#
#        Returns:
#            hook_name (str): The repeater hook, when created, is a
#                dynamically assigned function that gets assigned to a
#                variable with a name created by combining the arguments.
#
#        """
#        return "_oob_%s_every_%ss_for_sessid_%s" % (oobfuncname, interval, sessid)
#
#    def _get_fieldmonitor_name(self, fieldname):
#        """
#        Get the fieldmonitor name.
#
#        Args:
#            fieldname (str): The field monitored.
#
#        Returns:
#            fieldmonitor_name (str): A dynamic function name
#                created from the argument.
#
#        """
#        return "_oob_at_%s_postsave" % fieldname
#
#    def _add_monitor(self, obj, sessid, fieldname, oobfuncname, *args, **kwargs):
#        """
#        Helper method. Creates a fieldmonitor and store it on the
#        object. This tracker will be updated whenever the given field
#        changes.
#
#        Args:
#            obj (Object): The object on which to store the monitor.
#            sessid (int): The Session id associated with the monitor.
#            fieldname (str): The field to monitor
#            oobfuncname (str): The OOB callback function to trigger when
#                field `fieldname` changes.
#            args, kwargs (any): Arguments to pass on to the callback.
#
#        """
#        fieldmonitorname = self._get_fieldmonitor_name(fieldname)
#        if not hasattr(obj, fieldmonitorname):
#            # assign a new fieldmonitor to the object
#            _SA(obj, fieldmonitorname, FieldMonitor(obj))
#        # register the session with the monitor
#        _GA(obj, fieldmonitorname).add(sessid, oobfuncname, *args, **kwargs)
#
#        # store calling arguments as a pickle for retrieval at reload
#        storekey = (pack_dbobj(obj), sessid, fieldname, oobfuncname)
#        stored = (args, kwargs)
#        self.oob_monitor_storage[storekey] = stored
#
#    def _remove_monitor(self, obj, sessid, fieldname, oobfuncname=None):
#        """
#        Helper method. Removes the OOB from obj.
#
#        Args:
#            obj (Object): The object from which to remove the monitor.
#            sessid (int): The Session id associated with the monitor.
#            fieldname (str): The monitored field from which to remove the monitor.
#            oobfuncname (str): The oob callback function.
#
#        """
#        fieldmonitorname = self._get_fieldmonitor_name(fieldname)
#        try:
#            _GA(obj, fieldmonitorname).remove(sessid, oobfuncname=oobfuncname)
#            if not _GA(obj, fieldmonitorname).subscribers:
#                _DA(obj, fieldmonitorname)
#        except AttributeError:
#            pass
#        # remove the pickle from storage
#        store_key = (pack_dbobj(obj), sessid, fieldname, oobfuncname)
#        self.oob_monitor_storage.pop(store_key, None)
#
#    def save(self):
#        """
#        Handles saving of the OOBHandler data when the server reloads.
#        Called from the Server process.
#
#        """
#        # save ourselves as a tickerhandler
#        super(OOBHandler, self).save()
#        # handle the extra oob monitor store
#        if self.ticker_storage:
#            ServerConfig.objects.conf(key=self.oob_save_name,
#                                      value=dbserialize(self.oob_monitor_storage))
#        else:
#            # make sure we have nothing lingering in the database
#            ServerConfig.objects.conf(key=self.oob_save_name, delete=True)
#
#    def restore(self):
#        """
#        Called when the handler recovers after a Server reload. Called
#        by the Server process as part of the reload upstart. Here we
#        overload the tickerhandler's restore method completely to make
#        sure we correctly re-apply and re-initialize the correct
#        monitor and repeater objecth on all saved objects.
#
#        """
#        # load the oob monitors and initialize them
#        oob_storage = ServerConfig.objects.conf(key=self.oob_save_name)
#        if oob_storage:
#            self.oob_storage = dbunserialize(oob_storage)
#            for store_key, (args, kwargs) in self.oob_storage.items():
#                # re-create the monitors
#                obj, sessid, fieldname, oobfuncname = store_key
#                obj = unpack_dbobj(obj)
#                self._add_monitor(obj, sessid, fieldname, oobfuncname, *args, **kwargs)
#        # handle the tickers (same as in TickerHandler except we  call
#        # the add_repeater method which makes sure to add the hooks before
#        # starting the tickerpool)
#        ticker_storage = ServerConfig.objects.conf(key=self.save_name)
#        if ticker_storage:
#            self.ticker_storage = dbunserialize(ticker_storage)
#            for store_key, (args, kwargs) in self.ticker_storage.items():
#                obj, interval, idstring = store_key
#                obj = unpack_dbobj(obj)
#                # we saved these in add_repeater before, can now retrieve them
#                sessid = kwargs["_sessid"]
#                oobfuncname = kwargs["_oobfuncname"]
#                self.add_repeater(obj, sessid, oobfuncname, interval, *args, **kwargs)
#
#    def add_repeater(self, obj, session, oobfuncname, interval=20, *args, **kwargs):
#        """
#        Set an oob function to be repeatedly called.
#
#        Args:
#            obj (Object); The object on which to register the repeat.
#            session (Session): Session of the session registering.
#            oobfuncname (str): Oob function name to call every interval seconds.
#            interval (int, optional): Interval to call oobfunc, in seconds.
#
#        Notes:
#            *args, **kwargs are used as extra arguments to the oobfunc.
#        """
#        sessid = session
#        hook = OOBAtRepeater()
#        hookname = self._get_repeater_hook_name(oobfuncname, interval, sessid)
#        _SA(obj, hookname, hook)
#        # we store these in kwargs so that tickerhandler saves them with the rest
#        kwargs.update({"_sessid":sessid, "_oobfuncname":oobfuncname})
#        super(OOBHandler, self).add(obj, int(interval), oobfuncname, hookname, *args, **kwargs)
#
#    def remove_repeater(self, obj, session, oobfuncname, interval=20):
#        """
#        Remove the repeatedly calling oob function
#
#        Args:
#            obj (Object): The object on which the repeater sits
#            sessid (Session): Session that registered the repeater
#            oobfuncname (str): Name of oob function to call at repeat
#            interval (int, optional): Number of seconds between repeats
#
#        """
#        sessid = session.sessid
#        super(OOBHandler, self).remove(obj, interval, idstring=oobfuncname)
#        hookname = self._get_repeater_hook_name(oobfuncname, interval, sessid)
#        try:
#            _DA(obj, hookname)
#        except AttributeError:
#            pass
#
#    def add_field_monitor(self, obj, session, field_name, oobfuncname, *args, **kwargs):
#        """
#        Add a monitor tracking a database field
#
#        Args:
#            obj (Object): The object who'se field is to be monitored.
#            session (Session): Session monitoring.
#            field_name (str): Name of database field to monitor. The db_* can optionally
#                be skipped (it will be automatically appended if missing).
#            oobfuncname (str): OOB function to call when field changes.
#
#        Notes:
#            When the field updates the given oobfunction will be called as
#
#                `oobfuncname(session, fieldname, obj, *args, **kwargs)`
#
#            where `fieldname` is the name of the monitored field and
#            `obj` is the object on which the field sits. From this you
#            can also easily get the new field value if you want.
#
#        """
#        sessid = session.sessid
#        # all database field names starts with db_*
#        field_name = field_name if field_name.startswith("db_") else "db_%s" % field_name
#        self._add_monitor(obj, sessid, field_name, oobfuncname, *args, **kwargs)
#
#    def remove_field_monitor(self, obj, session, field_name, oobfuncname=None):
#        """
#        Un-tracks a database field
#
#        Args:
#            obj (Object): Entity with the monitored field.
#            session (Session): Session that monitors.
#            field_name (str): database field monitored (the db_* can optionally be
#                skipped (it will be auto-appended if missing).
#            oobfuncname (str, optional): OOB command to call on that field.
#
#        Notes:
#            When the Attributes db_value updates the given oobfunction
#            will be called as
#
#                `oobfuncname(session, fieldname, obj, *args, **kwargs)`
#
#            where `fieldname` is the name of the monitored field and
#            `obj` is the object on which the field sits. From this you
#            can also easily get the new field value if you want.
#        """
#        sessid = session.sessid
#        field_name = field_name if field_name.startswith("db_") else "db_%s" % field_name
#        self._remove_monitor(obj, sessid, field_name, oobfuncname=oobfuncname)
#
#    def add_attribute_monitor(self, obj, session, attr_name, oobfuncname, *args, **kwargs):
#        """
#        Monitor the changes of an Attribute on an object. Will trigger when
#        the Attribute's `db_value` field updates.
#
#        Args:
#            obj (Object): Object with the Attribute to monitor.
#            session (Session): Session monitoring Session.
#            attr_name (str): Name (key) of Attribute to monitor.
#            oobfuncname (str): OOB function to call when Attribute updates.
#
#        """
#        sessid = session.sessid
#        # get the attribute object if we can
#        attrobj = obj.attributes.get(attr_name, return_obj=True)
#        if attrobj:
#            self._add_monitor(attrobj, sessid, "db_value", oobfuncname)
#
#    def remove_attribute_monitor(self, obj, session, attr_name, oobfuncname):
#        """
#        Deactivate tracking for a given object's Attribute
#
#        Args:
#            obj (Object): Object monitored.
#            session (Session): Session monitoring.
#            attr_name (str): Name of Attribute monitored.
#            oobfuncname (str): OOB function name called when Attribute updates.
#
#        """
#        sessid = session.sessid
#        attrobj = obj.attributes.get(attr_name, return_obj=True)
#        if attrobj:
#            self._remove_monitor(attrobj, sessid, "db_value", oobfuncname)
#
#    def get_all_monitors(self, session):
#        """
#        Get the names of all variables this session is tracking.
#
#        Args:
#            session (Session): Session monitoring.
#        Returns:
#            stored monitors (tuple): A list of tuples
#                `(obj, fieldname, args, kwargs)` representing all
#                the monitoring the Session with the given sessid is doing.
#
#        """
#        sessid = session.sessid
#        # [(obj, fieldname, args, kwargs), ...]
#        return [(unpack_dbobj(key[0]), key[2], stored[0], stored[1])
#                for key, stored in self.oob_monitor_storage.items() if key[1] == sessid]

# access object
MONITOR_HANDLER = MonitorHandler()
