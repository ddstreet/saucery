
// service name, e.g. 'sos', 'case', 'customer', 'machineid', 'hostname', etc...
var SauceryService;
// service value, e.g. sosreport name for 'sos', case number for 'case', etc...
var SauceryServiceValue;
// service path, i.e. any path after key; used mostly for 'sos', e.g. /files/...
var SauceryServicePath;

if (window.location.pathname.endsWith('.html')) {
    SauceryService = window.location.pathname.split('/').slice(-1)[0].split('.')[0];
    let value = new URLSearchParams(window.location.search).get(SauceryService).split('/');
    SauceryServiceValue = value[0];
    SauceryServicePath = value.slice(1).join('/');
} else {
    let path = window.location.pathname.split('/');
    SauceryService = path[1];
    SauceryServiceValue = path[2];
    SauceryServicePath = path.slice(3).join('/');
}

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
        filterfunction = (entry => encodeURIComponent(entry[params.field || SauceryService]) == (params.value || SauceryServiceValue));

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

            $('.' + field).append(JoinAnchors(anchors));
        });

        SauceryTable('.SauceryTable', SOSEntries, tableFields, tableHeaders, anchorFunctions);
        ConclusionsTree('.ConclusionsTree');
        FilesTree('.FilesTree');
    });
}

function SauceryAnchor(entry, field, anchorFunction) {
    if (anchorFunction === undefined)
        anchorFunction = SauceryAnchorFunctions[field];

    return (anchorFunction ?
            anchorFunction(entry[field], entry) :
            $('<a>').text(entry[field]));
}

function SauceryTable(elements,
                      entries,
                      fields=SauceryTableFields,
                      headers=SauceryTableHeaders,
                      anchorFunctions=SauceryAnchorFunctions) {
    if (elements.length == 0)
        return;

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

    table.appendTo(elements).DataTable({
        'pageLength': 25,
        'order': [[ 4, 'desc' ], [ 2, 'desc' ]],
    });
}

function FilesTree(elements) {
    if (elements.length == 0)
        return;

    let sospath = SauceryServicePath.split('/').filter(p => p).reverse();

    if (sospath.length == 0) {
        $('<a>').attr('href', 'files').text('files').appendTo(elements);
        return;
    }

    let href = '';
    let anchors = sospath.map(function (name) {
        let a = $('<a>').attr('href', href).text(name);
        href = href + '../';
        return a;
    }).reverse();
    $('<p>').append(JoinAnchors(anchors, '/')).appendTo(elements);

    let jstree_data = function (obj, callback) {
        let path = this.get_path(obj, '/') || '';
        $.getJSON(path, {'format': 'json'}, function (data) {
            callback(data.map(function (child) {
                let href = (path ? path + '/' : '') + encodeURIComponent(child.name);
                return {
                    'text': child.name,
                    'icon': false,
                    'a_attr': {
                        'href': href,
                    },
                    'href': href,
                    'children': child.type == 'directory',
                }
            }));
        });
    };

    $('<p>').jstree({'core': {'data': jstree_data}})
        .on('select_node.jstree', (evt, data) => window.location = data.node.original.href)
        .appendTo(elements);
}

function ConclusionsTree(elements) {
    if (elements.length == 0)
        return;

    $.getJSON('conclusions', {'format': 'json'}, (data => PopulateConclusionsTree(data, elements)));
}

function PopulateConclusionsTree(data, elements) {
    let tree = $('<div>');
    let ul = $('<ul>').appendTo(tree);
    let levels = new Map();

    data.forEach(entry => {
        if (!entry.abnormal)
            return;
        if (!levels.has(entry.level))
            levels.set(entry.level, new Array());
        entry.results.forEach(result => levels.get(entry.level).push(result));
    });

    let issues = ['critical', 'error', 'warning'];
    let info = ['info'];

    issues.concat(info).forEach(level => {
        if (levels.has(level)) {
            let li = $('<li>').text(level[0].toUpperCase() + level.slice(1) + 's').appendTo(ul);
            let sublist = $('<ul>').appendTo(li);
            if (issues.includes(level))
                li.addClass('jstree-open');
            levels.get(level).forEach(result => $('<li>').text(result).appendTo(sublist));
        }
    });

    tree.jstree({
        'core': {
            'themes': {
                'icons': false,
            },
        },
    }).appendTo(elements);
}

function JoinAnchors(anchors, separatortext=', ') {
    let list = anchors.flatMap(a => [a, $('<a>').text(separatortext)]);
    list.pop();
    return list;
}

function DateToYMD(date) {
    return (String(date.getUTCFullYear()).padStart(4, '0') + '-' +
            String(date.getUTCMonth()+1).padStart(2, '0') + '-' +
            String(date.getUTCDate()).padStart(2, '0'));
}

function ConclusionsSummary(conclusions) {
    let p = $('<p>');

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
