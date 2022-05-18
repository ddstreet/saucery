
function FilesTree() {
    let div = $('<div>');
    let sospath = SauceryServicePath.split('/').filter(p => p).reverse();

    if (sospath.length == 0) {
        return $('<a>').attr('href', 'files').text('files');
    }

    let href = '';
    let anchors = sospath.map(function (name) {
        let a = $('<a>').attr('href', href).text(name);
        href = href + '../';
        return a;
    }).reverse();
    anchors.slice(1).forEach(a => $('<a>').text('/').insertBefore(a));
    $('<div>').append(anchors).appendTo(div);

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

    $('<div>').appendTo(div).jstree({'core': {'data': jstree_data}})
        .on('select_node.jstree', (evt, data) => window.location = data.node.original.href);
    return div;
}
