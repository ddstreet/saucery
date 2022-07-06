
var SauceryParams = new URLSearchParams(window.location.search);
var SauceryPath = window.location.pathname;
var SauceryPathEntries = SauceryPath.split('/');

// service name, e.g. 'sos', 'case', 'customer', 'machineid', 'hostname', etc...
var SauceryService = SauceryPathEntries[1];
// service value, e.g. sosreport name for 'sos', case number for 'case', etc...
var SauceryServiceValue = SauceryPathEntries[2];
// service path, i.e. any path after key; used mostly for 'sos', e.g. /files/...
var SauceryServicePathEntries = SauceryPathEntries.slice(3).filter(p => p);
var SauceryServicePath = SauceryServicePathEntries.join('/');
// relative path back to our SauceryServicePath dir
var SauceryServicePathRoot = '../'.repeat(SauceryServicePathEntries.length);
// service sub-value, e.g. 'files' for sos-*/files/
var SaucerySubServiceValue = SauceryServicePathEntries[0];
// service sub-path, e.g. path after key/files/
var SaucerySubServicePathEntries = SauceryServicePathEntries.slice(1);
var SaucerySubServicePath = SaucerySubServicePathEntries.join('/');
// relative path back to our SaucerySubServicePath dir
var SaucerySubServicePathRoot = '../'.repeat(SaucerySubServicePathEntries.length);

var SauceryMenu = [];
var SauceryMenuLoaded = $.getJSON('/menu.json', data => SauceryMenu = data);
function SauceryMenuReady(callback) {
    $.when(SauceryMenuLoaded).done(callback);
}

// Set link to main index
$(() => $('.mainindex').css('text-align', 'center').append($('<a>').attr('href', '/').text('Return to main index')));

// keys are fields, values are functions to generate hrefs
var SauceryAnchorFunctions = {
    'case': ((v, e) => CreateAnchor(v, '/case/' + v)),
    'customer': ((v, e) => CreateAnchor(v, '/customer/' + v, 30)),
    'hostname': ((v, e) => CreateAnchor(v, '/hostname/' + v, 20)),
    'machineid': ((v, e) => CreateAnchor(v, '/machineid/' + v, 12)),
    'name': ((v, e) => CreateAnchor(v, '/sos/' + v, 30)),
    'sosreport': ((v, e) => CreateAnchor(v, '/sos/' + v)),
    'datetime': ((v, e) => CreateAnchor(DateToYMD(new Date(v)))),
    'conclusions': ((v, e) => ConclusionsSummary(v)),
}
// entry fields that should be updated on page load
var SauceryAnchorFields = [
    'case',
    'customer',
    'hostname',
    'machineid',
    'name',
    'sosreport',
]

// keys are fields, values are header text
var SauceryTableHeaders = {
    'customer': 'Customer',
    'case': 'Case',
    'hostname': 'Hostname',
    'machineid': 'Machine ID',
    'datetime': 'Date',
    'name': 'SOS',
    'conclusions': 'Conclusions',
}
// table column fields, in order they should be displayed
var SauceryTableFields = Object.keys(SauceryTableHeaders);

// params is an object with optional fields:
//   filter: a function passed to entries.filter(); this overrides field/value filtering
//   field: a field of each entry to filter on, default SauceryService
//   value: the value to match each entry field with, default SauceryServiceValue
//   anchorFields: Array of fields to update DOM elements, default SauceryAnchorFields
//   anchorFunctions: Object in same format as default, SauceryAnchorFunctions
//   tableFields: Array of fields to include in table, default SauceryTableFields
//   tableHeaders: Object in same format as default, SauceryTableHeaders
function SelectSOSEntries(params={}) {
    if (params.filter)
        filterfunction = params.filter;
    else
        filterfunction = (entry => entry[params.field || SauceryService] == decodeURIComponent(params.value || SauceryServiceValue));

    anchorFields = params.anchorFields || SauceryAnchorFields;
    anchorFunctions = params.anchorFunctions || SauceryAnchorFunctions;
    tableFields = params.tableFields || SauceryTableFields;
    tableHeaders = params.tableHeaders || SauceryTableHeaders;

    SauceryMenuReady(function () {
        let SOSEntries = SauceryMenu.filter(filterfunction);

        anchorFields.forEach(function (field) {
            let entries = SOSEntries.filter(entry => entry[field])
                .reduce(function (list, entry) {
                    if (!list.map(entry => entry[field]).includes(entry[field]))
                        list.push(entry);
                    return list;
                }, [])
                .sort((a, b) => a[field].toString().localeCompare(b[field].toString()));

            let anchors = entries.map(function (entry) {
                return SauceryAnchor(entry, field, anchorFunctions[field]);
            });

            anchors.slice(1).forEach(a => $('<a>').text(',').insertBefore(a));
            $('.' + field).append(anchors);
        });

        $('.SauceryTable').append(SauceryTable(SOSEntries, tableFields, tableHeaders, anchorFunctions));
    });
}

function SauceryTable(entries,
                      fields=SauceryTableFields,
                      headers=SauceryTableHeaders,
                      anchorFunctions=SauceryAnchorFunctions) {
    let table = $('<table>');
    let thead = $('<thead>').appendTo(table);
    let tbody = $('<tbody>').appendTo(table);

    let tr = $('<tr>').appendTo(thead);
    fields.forEach(function (field) {
        let header = headers[field] || field;
        $('<th>').text(header).appendTo(tr);
    });

    entries.forEach(function (entry) {
        let tr = $('<tr>').appendTo(tbody);
        fields.forEach(function (field) {
            let anchor = SauceryAnchor(entry, field, anchorFunctions[field]);
            $('<td>').append(anchor).appendTo(tr);
        });
    });

    table.DataTable({
        'pageLength': 25,
        'order': [[ 4, 'desc' ], [ 2, 'desc' ]],
    });
    return table;
}

function SauceryAnchor(entry, field, anchorFunction) {
    if (anchorFunction === undefined)
        anchorFunction = SauceryAnchorFunctions[field];

    return (anchorFunction ?
            anchorFunction(entry[field], entry) :
            $('<a>').text(entry[field]));
}

function DateToYMD(date) {
    return (String(date.getUTCFullYear()).padStart(4, '0') + '-' +
            String(date.getUTCMonth()+1).padStart(2, '0') + '-' +
            String(date.getUTCDate()).padStart(2, '0'));
}

function CreateAnchor(text, href, maxlen) {
    let a = $('<a>').text(LimitLength(text, maxlen));

    if (href)
        a.attr('href', href)

    return a;
}

function LimitLength(value, length) {
    if (!value || !length)
        return value;

    let v = value.slice(0, length - 1);

    if (v.length < value.length)
        v = v + '\u2026';

    return v;
}

function ConclusionsSummary(conclusions) {
    let p = $('<p>');

    if (!conclusions) {
        $('<a>').text('?').appendTo(p);
        return p;
    }

    if (conclusions.critical > 0)
        p.append($('<a>').text('Critical: ' + conclusions.critical).addClass('critical')).append('<br>');
    if (conclusions.error > 0)
        p.append($('<a>').text('Error: ' + conclusions.error).addClass('error')).append('<br>');
    if (conclusions.warning > 0)
        p.append($('<a>').text('Warning: ' + conclusions.warning).addClass('warning')).append('<br>');
    if (conclusions.info > 0)
        p.append($('<a>').text('Info: ' + conclusions.info)).append('<br>');

    return p;
}
