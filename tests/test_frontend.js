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
function jquery(arg) { if (typeof arg === 'function') arg(); return {modal() {}}; }
function notify() {}
notify.prototype.options = {confirm: {buttons: []}};
const context = {
    $: jquery, PNotify: notify, gettext: x => x, OCTOPRINT_VIEWMODELS: [],
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
