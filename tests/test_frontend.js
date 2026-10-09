// Exercise the real view model's credential lifecycle without a printer/browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function observable(value) {
    const fn = function(next) { if (arguments.length) value = next; return value; };
    fn.subscribe = () => {};
    return fn;
}
function array(value = []) {
    const fn = observable(value);
    fn.push = item => fn().push(item);
    fn.remove = item => fn(fn().filter(x => x !== item));
    return fn;
}
function plain(value) {
    if (typeof value === 'function') return plain(value());
    if (Array.isArray(value)) return value.map(plain);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, plain(v)]));
    return value;
}
let warningVisible = false;
let request;
function jquery(arg) {
    if (typeof arg === 'function') arg();
    return {modal(action) { warningVisible = action === 'show'; }, is() { return warningVisible; }};
}
jquery.ajax = options => {
    request = {options};
    const chain = {done(fn) { request.done = fn; return chain; }, fail(fn) { request.fail = fn; return chain; }};
    return chain;
};
function notify() {}
notify.prototype.options = {confirm: {buttons: []}};
const context = {
    API_BASEURL: '/api/', moment: () => ({subtract() { return this; }, format() { return '2026-10-09T12:00'; }}), $: jquery, PNotify: notify, gettext: x => x, OCTOPRINT_VIEWMODELS: [],
    ko: {
        observable, observableArray: array, computed: fn => fn, pureComputed: fn => fn,
        observableDictionary: () => ({items: array(), pushAll() {}}),
        utils: {arrayForEach: (a, fn) => a.forEach(fn), arrayFilter: (a, fn) => a.filter(fn), arrayFirst: (a, fn) => a.find(fn)},
        toJS: plain, toJSON: value => JSON.stringify(plain(value))
    }
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('octoprint_tplinksmartplug/static/js/tplinksmartplug.js', 'utf8'), context);
const Constructor = context.OCTOPRINT_VIEWMODELS[0][0];
const plug = {ip: observable('192.0.2.1'), backend: observable('tapo')};
const settings = {settings: {plugins: {tplinksmartplug: {arrSmartplugs: array([plug])}}}};
const model = new Constructor([settings, {isAdmin: () => true}, {getAdditionalData: () => ''}]);
model.onBeforeBinding();
assert.equal(plug.tapoPassword(), '');
assert.equal(plug.tapoPasswordSet(), false);
plug.tapoUsername('test@example.invalid');
plug.tapoPassword('test-password-only');
model.selectedPlug(plug);
assert.equal(model.publicPlugs()[0].tapoPassword, undefined, 'navbar data must omit entered passwords');
assert.equal(plug.tapoPassword(), 'test-password-only', 'sanitizing a navbar copy must not erase an unsaved input');
model.onSettingsHidden();
assert.equal(plug.tapoPassword(), '', 'closing settings must clear the input');
const serverPlug = {ip: observable('192.0.2.1'), tapoUsername: observable('test@example.invalid'), tapoPasswordSet: observable(true)};
settings.settings.plugins.tplinksmartplug.arrSmartplugs([serverPlug]);
model.onSettingsShown();
assert.equal(model.arrSmartplugs()[0], serverPlug, 'reopened settings must use the server response');
assert.equal(serverPlug.tapoPassword(), '');
assert.equal(serverPlug.tapoPasswordSet(), true);
model.addPlug();
assert.equal(model.selectedPlug().tapoUsername(), '');
assert.equal(model.selectedPlug().tapoPassword(), '');
assert.equal(model.selectedPlug().tapoClearCredentials(), false);
console.log('Frontend credential lifecycle passed');

warningVisible = false;
const relay = {
    ip: observable('192.0.2.2'), label: observable('Printer plug'),
    currentState: observable('unknown'), emeter: {get_realtime: {}},
    backend: observable('tapo'), displayWarning: observable(true), warnPrinting: observable(true)
};
model.arrSmartplugs([relay]);
let permitted = true;
const permission = [{method: 'role', value: ['plugin_tplinksmartplug_control']}];
model.access = {permissions: {PLUGIN_TPLINKSMARTPLUG_CONTROL: permission}};
model.loginState.hasPermission = key => permitted && key === permission;
assert.equal(model.plugStateText(relay), 'Unknown');
model.sidebarTurnOn(relay);
assert.equal(JSON.parse(request.options.data).command, 'turnOn', 'unknown Tapo state must still allow switching on');
assert.equal(model.canControlPlug(relay), false, 'pending requests must disable controls');
assert.equal(model.plugStateText(relay), 'Working...');
request.done({ip: relay.ip(), currentState: 'on', emeter: null});
assert.equal(model.plugStateText(relay), 'On');
assert.equal(model.canControlPlug(relay), true);
const previous = request;
model.sidebarTurnOff(relay);
assert.equal(warningVisible, true, 'sidebar off must preserve confirmation');
assert.equal(request, previous, 'no off request before confirmation');
model.cancelClick(relay);
warningVisible = false;
assert.equal(model.canControlPlug(relay), true, 'cancel must restore controls');
model.sidebarTurnOff(relay);
model.turnOff(relay);
assert.equal(JSON.parse(request.options.data).command, 'turnOff');
request.fail();
assert.equal(model.canControlPlug(relay), true, 'HTTP errors must not leave the plug busy');
assert.equal(relay.currentState(), 'on', 'failed writes must not invent a new relay state');
permitted = false;
const deniedRequest = request;
model.sidebarTurnOn(relay);
assert.equal(request, deniedRequest, 'users without control permission cannot switch');
console.log('Sidebar relay controls passed');

settings.settings.plugins.tplinksmartplug.password = observable('dummy-default-password');
model.onSettingsHidden();
assert.equal(settings.settings.plugins.tplinksmartplug.password(), '', 'closing settings must clear the new default-account password input');
model.add_discovered_device('192.0.2.3', 'Discovered plug');
model.editPlug(model.selectedPlug());
assert.equal(model.selectedPlug().backend(), 'kasa', 'discovered devices should use upstream python-kasa');
assert.equal(model.selectedPlug().tapoPassword(), '');
assert.equal(model.selectedPlug().useCountdownRules(), false);
console.log('2.0 default account and discovered-device editor passed');
