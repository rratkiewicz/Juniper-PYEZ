#
# Author: Ryan Ratkiewicz (<ryan@ryanrat.com>)
# check_jsrx_session.py
# Last-Modified:  2015-12-23
#
# get_session.py was originally intended to pull a specific session from the Juniper SRX Firewall via PYEZ from a Nagios host.
# The script relies upon version 2.7 of Python, although earlier versions may also work. 
# 
# Example:
# python check_jsrx_session.py myfirewall.corp.com
# 		Will return all sessions in the firewall in a pretty print format.
#
# python check_jsrx_session.py myfirewall.corp.com --src_address x.x.x.x --dst_address y.y.y.y --dst_port 80 --protocol tcp
#		Will return all sessions that match specified criteria.
#
# python check_jsrx_session.py myfirewall.corp.com --src_address x.x.x.x --dst_address y.y.y.y --dst_port 80 --protocol tcp --nagios
#		Will return all sessions that match specified criteria, but evaluate only the first match in a Nagios output format.
#		Output Example:
#			SESSION OK - Session ID 31432 | bytes_in=17515 bytes_out=4786 configured_timeout=43200 timeout=43094
#
# python check_jsrx_session.py --username XXXXXX --password YYYYYYY
#		Will return all sessions, but leverage a username and password in lieu of SSH keys.


import sys
import argparse
#import ipaddress
from lxml import etree
import xml.etree.ElementTree as ET
from jnpr.junos import Device
from jnpr.junos.exception import ConnectError
import pprint

# get_session returns a list of dictionary items that contain Juniper SRX session data based upon the input criteria given.
# device is the only mandatory field for this, as if no other options are specified, all sessions will be returned.
# if the SRX is clustered, Backup sessions from the passive device are not included in the list.
# Since the SRX returns XML data, we parse the XML using etree, and place the corresponding data session elements inside a 
# dictionary.  We then also parse each flow or wing element of the session and add it to the dictionary.  
# In order to distinguish between 'in' and 'out' wings, we prepend the dictionary with the 'direction' element of the wing,
# thus giving us a unique key for the flow.

def get_session(source_ip,destination_ip,destination_port,protocol,device, username, password):
	if (username and password) != None:
		dev = Device(host=device, user=username, password=password)
	else :
		dev = Device(host=device)
	
	try:
		dev.open()
	except ConnectError as err:
		print "Cannot connect to device: {0}".format(err)
		sys.exit(1)


	flow_args = {}
	if source_ip != None :
		flow_args['source_prefix'] = source_ip 
		
	if destination_ip != None :
		flow_args['destination_prefix'] = destination_ip

	if destination_port != None :
		flow_args['destination_port'] = destination_port

	if protocol != None :
		flow_args['protocol'] = protocol
	
	flow_request = dev.rpc.get_flow_session_information(**flow_args)
	dev.close()

	root = ET.fromstring(etree.tostring(flow_request))
	session_list = []

	for session in root.findall('./multi-routing-engine-item/flow-session-information/flow-session'):
		session_state = session.find('session-state')
		session_identifier = session.find('session-identifier')
		policy = session.find('policy')
		configured_timeout = session.find('configured-timeout')
		timeout = session.find('timeout')
		start_time = session.find('start-time')
		duration = session.find('duration')

		session_dict = {'session-id' : session_identifier.text, 'session-state' : session_state.text, 'policy' : policy.text, 'timeout' : timeout.text, \
			'start-time' : start_time.text, 'duration' : duration.text, 'configured-timeout' : configured_timeout.text }

		flow_list = []

		for flow in session.findall('./flow-information'):
			direction = flow.find('direction')
			source_address = flow.find('source-address')
			destination_address = flow.find('destination-address')
			source_port = flow.find('source-port')
			destination_port = flow.find('destination-port')
			protocol = flow.find('protocol')
			byte_count = flow.find('byte-cnt')

			session_dict.update({ direction.text + ':source-address' : source_address.text, direction.text + ':destination-address' : destination_address.text, \
			direction.text + ':source_port' : source_port.text, direction.text + ':destination-port' : destination_port.text, direction.text + ':protocol' : protocol.text,\
			direction.text + ':byte-count' : byte_count.text })
			

		if session_state.text == 'Active' :
			session_list.append(session_dict.copy())

	return session_list;


# Main declares a standard parser and passes the arguments to get_session.  Once the output is returned back to main, we evaluate if args.nagios
# is being used, and if so, it returns output that will allow Nagios to evaluate the health of the service, and also pass perf data after the '|'
# (pipe) delimiter.  If Nagios is not specified, the main function returns a pretty printed version of the session data.

def main(argv):
	source_ip = None
	destination_ip = None
	destination_port = None
	protocol = None
	device = None


	parser = argparse.ArgumentParser()
	parser.add_argument("device",help="Specify the hostname or IP address of your Juniper SRX")
	parser.add_argument("--src_address", help="Source address or prefix of desired session(s)")
	parser.add_argument("--dst_address", help="Destination address or prefix of desired session(s)")
	parser.add_argument("--dst_port", help="Destination port of desired session(s)")
	parser.add_argument("--protocol", help="TCP or UDP, or any supported SRX protocol")
	parser.add_argument("--nagios", dest="nagios", action="store_true",  help="Nagios formatted output")
	parser.add_argument("--username", help="Username to firewall, in the event ssh-keys are not available")
	parser.add_argument("--password", help="Password to firewall, in the event ssh-keys are not available")

	args = parser.parse_args()

	session = get_session(args.src_address, args.dst_address, args.dst_port, args.protocol, args.device, args.username, args.password)

	if args.nagios :
		if len(session)> 0 :
			print 'SESSION OK - Session ID ' + session[0].get('session-id') + ' | bytes_in=' + session[0].get('In:byte-count') + ';bytes_out=' + session[0].get('Out:byte-count') \
			+ ';configured_timeout=' + session[0].get('configured-timeout') + ';timeout=' + session[0].get('timeout') + ';;'
		else:
			print "SESSION CRITICAL"
	else:
		pp = pprint.PrettyPrinter(indent=4)
		pp.pprint(session)


if __name__ == "__main__":
	main(sys.argv[1:])


