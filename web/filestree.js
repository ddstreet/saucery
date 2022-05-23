
$(FilesTree);

function FilesTree() {
    let filestree = $('.FilesTree');
    if (!filestree.length)
        return;

    let sospath = SauceryServicePath.split('/').filter(p => p).reverse();

    if (sospath.length == 0) {
        $('<a>').attr('href', 'files').text('files').appendTo(filestree);
        return;
    }

    let href = '';
    let anchors = sospath.flatMap(function (name) {
        let a = $('<a>').attr('href', href).text(name);
        href = href + '../';
        return [a, $('<a>').text('/')];
    }).slice(0, -1).reverse();
    $('<div>').append(anchors).appendTo(filestree);

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

    $('<div>').jstree({'core': {'data': jstree_data}})
        .on('select_node.jstree', (evt, data) => window.location = data.node.original.href)
        .appendTo(filestree);
}
